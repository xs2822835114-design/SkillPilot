"""缺口编排（阶段 4，gap_agent）：画像 + 目标 → SkillGapReport（规则可重复 + 可选 LLM 润色）。"""
from __future__ import annotations

import logging
from datetime import datetime

from psycopg.rows import dict_row

from app.config import Config
from app.gap import closure, explain, gap_score, graph_store
from app.gap.schemas import (
    GapAnalysisRequest,
    GapCoverage,
    GapItem,
    GapResponse,
    PrereqItem,
    SkillGapReport,
)
from app.persistence import db as pgdb
from app.profile.rule_engine import level_from_scores
from app.profile.skill_service import normalize_skill_id

logger = logging.getLogger(__name__)

CUSTOM_ROLE_ID = "__custom__"


def analyze(config: Config, request: GapAnalysisRequest) -> GapResponse:
    """编排缺口计算：对每个目标岗位产出一份 SkillGapReport；target_skills 为额外追加要求。

    标题信息说明：缺口计算（score/priority/reason/prereq）纯规则，不依赖 LLM；
    suggestions 可选 LLM 润色（失败走模板兜底）。
    """
    edges = graph_store.load_requires_edges(config)
    names = graph_store.load_skill_names(config)
    levels = _load_current_levels(config, request.user_id)
    actual_version = _load_profile_version(config, request.user_id)
    used_version = request.profile_version if request.profile_version is not None else actual_version

    extra_reqs = [_to_requirement(s) for s in request.target_skills]

    reports: list[SkillGapReport] = []
    for role_id in request.target_roles:
        role = graph_store.load_role(config, role_id)
        if role is None:
            raise ValueError(f"目标岗位不存在：{role_id}")
        reports.append(
            _single(config, request.user_id, role_id, role, extra_reqs, edges, names, levels, used_version, request.top_gaps)
        )

    if not request.target_roles and request.target_skills:
        from app.gap.graph_store import LoadedRole, RoleRequirement

        custom = LoadedRole(
            role_id=CUSTOM_ROLE_ID,
            role_name="自定义目标能力",
            category="Custom",
            requirements=[RoleRequirement(x.skill_id, x.name, x.required_level, x.weight) for x in extra_reqs],
        )
        reports.append(
            _single(config, request.user_id, CUSTOM_ROLE_ID, custom, [], edges, names, levels, used_version, request.top_gaps)
        )

    return GapResponse(reports=reports)


def _to_requirement(ts) -> graph_store.RoleRequirement:
    """TargetSkill → RoleRequirement（技能名归一为 id）。"""
    sid = normalize_skill_id(ts.skill)
    return graph_store.RoleRequirement(sid, ts.skill.strip(), ts.level, ts.weight)


def _single(
    config: Config,
    user_id: str,
    role_id: str,
    role: graph_store.LoadedRole,
    extra_reqs: list[graph_store.RoleRequirement],
    edges: list[tuple[str, str]],
    names: dict[str, str],
    levels: dict[str, int],
    used_version: int,
    top_gaps: int | None,
) -> SkillGapReport:
    limit = top_gaps if top_gaps is not None else config.gap_top_default
    req_by: dict[str, graph_store.RoleRequirement] = {}
    for r in role.requirements:
        req_by.setdefault(r.skill_id, r)
    for e in extra_reqs:
        req_by.setdefault(e.skill_id, e)  # target_roles 为主，target_skills 仅新增
    reqs = list(req_by.values())
    req_ids = set(req_by)

    covered_ids = [r.skill_id for r in reqs if levels.get(r.skill_id, 0) >= r.required_level]
    direct = [r for r in reqs if levels.get(r.skill_id, 0) < r.required_level]
    direct_ids = {r.skill_id for r in direct}
    mastered = {sid for sid, lv in levels.items() if lv > 0}

    # 每个直接缺口的传递前置闭包
    closure_for: dict[str, set[str]] = {
        r.skill_id: closure.transitive_prereqs(edges, r.skill_id) for r in direct
    }

    # 缺失前置：直接缺口闭包中，未掌握且不在岗位要求集合内的技能
    missing: set[str] = set()
    ref_weight: dict[str, float] = {}
    for r in direct:
        for p in closure_for[r.skill_id]:
            if p in mastered or p in req_ids:
                continue
            missing.add(p)
            ref_weight[p] = max(ref_weight.get(p, 0.0), r.weight)

    all_ids: set[str] = direct_ids | missing
    report_seq = closure.topo_sort(sorted(all_ids), edges)

    gap_items = _build_gap_items(config, all_ids, direct_ids, req_by, closure_for, ref_weight, edges, names, levels)
    gap_items.sort(key=lambda g: (-g.score, g.priority))
    gap_items = gap_items[: limit]
    coverage = GapCoverage(
        required_total=len(reqs),
        covered_skills=covered_ids,
        gap_skills=sorted(direct_ids),
        gap_total=len(direct_ids),
        coverage_rate=gap_score.coverage_rate(len(covered_ids), len(reqs)),
    )
    report = SkillGapReport(
        user_id=user_id,
        target_role_id=role_id,
        target_role=role.role_name,
        role_category=role.category,
        profile_version_used=used_version,
        generated_at=datetime.now().astimezone(),
        coverage=coverage,
        gaps=gap_items,
        recommended_sequence=report_seq,
    )
    polished = explain.llm_polish_suggestions(report)
    report.suggestions = polished or explain.build_suggestions(report)
    report.is_llm_enhanced = polished is not None
    return report


def _build_gap_items(
    config: Config,
    all_ids: set[str],
    direct_ids: set[str],
    req_by: dict[str, graph_store.RoleRequirement],
    closure_for: dict[str, set[str]],
    ref_weight: dict[str, float],
    edges: list[tuple[str, str]],
    names: dict[str, str],
    levels: dict[str, int],
) -> list[GapItem]:
    items: list[GapItem] = []
    for sid in all_ids:
        if sid in direct_ids:
            r = req_by[sid]
            req_level, disp_weight, decay = r.required_level, r.weight, 1.0
        else:
            req_level = max(
                (req_by[g].required_level for g in direct_ids if sid in closure_for.get(g, set())) or [0]
            )
            disp_weight, decay = ref_weight.get(sid, 0.5), config.gap_prereq_decay

        current_level = levels.get(sid, 0)
        delta = max(0, req_level - current_level)
        score = gap_score.gap_score(req_level, current_level, disp_weight, decay)
        pri = gap_score.priority(disp_weight, delta)

        # 前置展开（展示 + 自身推荐序列）：当前未掌握的前置，拓扑有序
        cands = [p for p in closure.transitive_prereqs(edges, sid) if levels.get(p, 0) == 0]
        ordered = closure.topo_sort(cands, edges)
        prereqs = [
            PrereqItem(
                skill_id=p,
                name=names.get(p, p),
                status="gap",
                own_gap_id=p if p in all_ids else None,
            )
            for p in ordered
        ]
        reason = explain.build_reason(
            names.get(sid, sid), req_level, current_level, disp_weight, [p.name for p in prereqs]
        )
        recommended_seq = ordered + [sid]
        items.append(
            GapItem(
                skill_id=sid,
                name=names.get(sid, sid),
                required_level=req_level,
                current_level=current_level,
                required_weight=disp_weight,
                score=score,
                priority=pri,
                reason=reason,
                prerequisites=prereqs,
                recommended_sequence=recommended_seq,
            )
        )
    return items


def _load_current_levels(config: Config, user_id: str) -> dict[str, int]:
    """读取画像当前技能等级（level 由规则换算；缺失视为 0）。"""
    with pgdb.connect(config) as conn:
        conn.row_factory = dict_row
        rows = conn.execute(
            """
            SELECT skill_id, theory_score, practice_score FROM user_skills WHERE user_id = %s
            """,
            (user_id,),
        ).fetchall()
    return {
        r["skill_id"]: level_from_scores(r["theory_score"] or 0, r["practice_score"] or 0, config.profile_practice_weight)
        for r in rows
    }


def _load_profile_version(config: Config, user_id: str) -> int:
    with pgdb.connect(config) as conn:
        conn.row_factory = dict_row
        row = conn.execute(
            "SELECT value FROM user_preferences WHERE user_id = %s AND key = '__profile_version__'",
            (user_id,),
        ).fetchone()
    if row is None or row["value"] is None:
        return 0
    return int(row["value"])