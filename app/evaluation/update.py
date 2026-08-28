"""评估回写与再规划编排（阶段 6，evaluation/update）。

评估完成后：① 用证据回写画像（阶段 3 apply_patch + 证据落库）；② 触发缺口再计算
并调用阶段 5 replan（可开关 trigger_replan）。全局异常不吞，由调用方兜底。
"""
from __future__ import annotations

import logging

from app.config import Config
from app.evaluation.schemas import EvaluationReport, EvaluationRequest
from app.practice import store as practice_store

logger = logging.getLogger(__name__)


def apply_report(config: Config, report: EvaluationReport, request: EvaluationRequest) -> EvaluationReport:
    """回写画像 + 按开关触发再规划，返回带 profile_updated/replanned 标记的报告。"""
    if not report.skill_id:
        return report

    practice = practice_store.load_practice(config, request.practice_id)
    score = next((s for s in report.skill_scores if s.skill_id == report.skill_id), None)
    if score is None:
        return report

    theory = score.theory
    practice_score = score.practice

    # ① 回写画像（追加本次评估证据）
    from app.profile import skill_service
    from app.profile import store as profile_store
    from app.profile.schemas import PatchSkill, SkillProfilePatch

    # user_skills.skill_id 外键约束到 skills：评估目标技能可能是 skill_nodes 学习节点
    #（如中文技能节点），需先确保其存在于技能字典，再回写。
    profile_store.ensure_skill_in_dict(config, report.skill_id)

    patch = SkillProfilePatch(
        user_id=request.user_id,
        skills=[
            PatchSkill(
                skill_id=report.skill_id,
                theory_score=theory,
                practice_score=practice_score,
                confidence=0.8,
                evidence=[report.evaluation_id],
            )
        ],
    )
    skill_service.apply_patch(config, patch)
    profile_store.save_evidence(
        config, report.evaluation_id, request.user_id,
        source_ref=request.practice_id, claim=f"代码实践评估，overall={report.overall_score}",
    )
    report.profile_updated = True

    # ② 触发再规划（默认取配置；开关为 false 时仅回写画像）
    trigger = request.trigger_replan if request.trigger_replan is not None else config.eval_trigger_replan_default
    if trigger and practice and practice.plan_id:
        try:
            from app.todo import planner as todo_planner
            from app.todo import todo_store
            from app.todo.schemas import ReplanRequest

            # 用『更新后画像』重算缺口，确保再规划反映本技能能力提升（而非沿用旧快照）
            replan_request = _fresh_gap_replan(config, request.user_id, practice.plan_id)
            todo_planner.replan(config, practice.plan_id, replan_request)
            report.replanned = True
        except Exception:  # noqa: BLE001
            # 重规划失败不影响评估本身（已回写画像）
            logger.warning("评估后重规划失败，仅保留画像更新", exc_info=True)
            report.replanned = False

    return report


def _fresh_gap_replan(config: Config, user_id: str, plan_id: str) -> ReplanRequest:
    """基于更新后的画像对该计划目标岗位重算缺口，返回带最新 gap_report 的重规划请求。"""
    from app.gap import gap_agent
    from app.gap.schemas import GapAnalysisRequest
    from app.todo import todo_store
    from app.todo.schemas import ReplanRequest

    role = None
    stored = todo_store.load_plan_report(config, plan_id)
    if stored and stored.get("target_role_id"):
        role = stored["target_role_id"]
    replan_request = ReplanRequest(weekly_hours=None)
    if role:
        resp = gap_agent.analyze(
            config, GapAnalysisRequest(user_id=user_id, target_roles=[role])
        )
        if resp.reports:
            replan_request = replan_request.model_copy(
                update={"gap_report": resp.reports[0]}
            )
    return replan_request