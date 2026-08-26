"""技能服务（阶段 3）：技能字典访问/归一、等级换算、增量合并策略。"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

from app.config import Config
from app.profile import rule_engine, store
from app.profile.schemas import PatchSkill, ProfileSkill, SkillProfile, SkillProfilePatch


def normalize_skill_id(name: str) -> str:
    """技能名 → 小写蛇形 id（与 seed_skills._slug 保持一致）。"""
    s = name.strip().lower()
    s = re.sub(r"[/\\()（）](s)?", "_", s)
    s = re.sub(r"[^a-z0-9\u4e00-\u9fff_]+", "_", s)
    return re.sub(r"_+", "_", s).strip("_")


# 仅有证据、无显式评分时的技能置信度基线（规则默认，非 LLM 打分）
_EVIDENCE_ONLY_CONFIDENCE = 0.5


def apply_patch(config: Config, patch: SkillProfilePatch) -> SkillProfile:
    """合并增量 patch 进已有画像并落库，返回合并后的完整画像。"""
    current = store.load_profile(config, patch.user_id)
    merged = _merge_skills(current, patch, config)
    _merge_preferences(current.preferences, patch.preferences)
    current.version += 1
    current.updated_at = datetime.now(timezone.utc)
    store.save_patch(config, patch.user_id, merged)
    return current


def register_project(config: Config, user_id: str, project_id: str, name: str, description: str, skills: list[str]) -> SkillProfile:
    """登记项目：绑定技能（简介自动抽取或显式指定）并合并进画像。"""
    from app.profile.schemas import ProjectInfo

    sid_list = [normalize_skill_id(s) for s in skills] or extract_skills_from_project(config, description)
    store.upsert_project(config, user_id, ProjectInfo(project_id=project_id, name=name, skills=sid_list))

    if not sid_list:
        return store.load_profile(config, user_id)

    patch = SkillProfilePatch(
        user_id=user_id,
        skills=[
            PatchSkill(skill_id=s, theory_score=None, practice_score=None, confidence=None, evidence=[project_id])
            for s in sid_list
        ],
    )
    return apply_patch(config, patch)


def _merge_skills(
    current: SkillProfile, patch: SkillProfilePatch, config: Config
) -> SkillProfile:
    names = _skill_names_map(config)
    by_id = {s.skill_id: s for s in current.skills}
    now = datetime.now(timezone.utc)

    for ps in patch.skills:
        sid = normalize_skill_id(ps.skill_id)

        prev = by_id.get(sid)
        is_new = prev is None
        if prev is None:
            prev = ProfileSkill(skill_id=sid, name=names.get(sid, ""))
            by_id[sid] = prev

        if ps.theory_score is not None:
            prev.theory_score = ps.theory_score
        if ps.practice_score is not None:
            prev.practice_score = ps.practice_score
        prev.level = rule_engine.level_from_scores(
            prev.theory_score, prev.practice_score, config.profile_practice_weight
        )
        if ps.confidence is not None:
            # 新技能直接用传入置信度，不按旧值稀释；已有技能走合并公式
            prev.confidence = ps.confidence if is_new else rule_engine.merge_confidence(
                prev.confidence, ps.confidence
            )
        elif is_new and ps.evidence:
            # 仅证据、无评分：给一个规则基线，避免被 min_confidence 过滤掉
            prev.confidence = _EVIDENCE_ONLY_CONFIDENCE
        if ps.evidence:
            prev.evidence = list(dict.fromkeys([*prev.evidence, *ps.evidence]))
            prev.last_proven_at = now

    current.skills = [
        s for s in by_id.values() if s.confidence >= config.profile_min_confidence
    ]
    return current


def _merge_preferences(dst: dict[str, Any], src: dict[str, Any]) -> None:
    dst.update(src)


def _skill_names_map(config: Config) -> dict[str, str]:
    return {row["id"]: row["name"] for row in store.load_skill_names(config)}


def extract_skills_from_project(config: Config, description: str) -> list[str]:
    """项目简介 → 命中技能字典的技能 id 列表（朴素子串匹配，非 LLM）。"""
    names = store.load_skill_names(config)
    text = description.lower()
    found: list[str] = []
    for row in names:
        name = (row["name"] or "").lower()
        if name and name in text:
            found.append(row["id"])
    return found