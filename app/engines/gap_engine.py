"""缺口引擎（方案第 12、13、14 节）：TargetProfile + UserSkillProfile → SkillGap。

确定性、可重复、可单测：缺口计算不依赖 LLM，而是结合「目标技能要求」与
「用户当前技能等级」做差，并根据前置关系对优先级加权。
"""
from __future__ import annotations

from app.config import Config
from app.domain import SkillGap, TargetProfile, UserSkillProfile
from app.gap import closure
from app.knowledge import _json_source


def _requires_edges() -> list[tuple[str, str]]:
    g = _json_source.load_graph()
    return [(s, t) for s, t, rel in g["edges"] if rel == "requires"]


def compute_gaps(config: Config, target: TargetProfile, user: UserSkillProfile) -> list[SkillGap]:
    """计算目标画像相对用户画像的技能缺口（仅返回真正存在差距的技能）。

    优先级 = 目标权重 × (gap/5) + 前置影响力加成：
    - ``source == "prerequisite"`` 的技能给固定加分（影响后续学习）；
    - 被越多「存在缺口的目标技能」依赖的前置，优先级越高。
    """
    user_level = {s.skill_id: (s.level if s.level is not None else 0) for s in user.skills}
    edges = _requires_edges()
    req_ids = {r.skill_id for r in target.skills}

    gaps: list[SkillGap] = []
    for r in target.skills:
        current = user_level.get(r.skill_id, 0)
        gap = max(0, r.required_level - current)
        if gap <= 0:
            continue

        # 有多少「处于缺口的目标技能」依赖当前技能作为（传递）前置
        dependents = sum(
            1
            for s in req_ids
            if s != r.skill_id and r.skill_id in closure.transitive_prereqs(edges, s)
        )

        priority = r.weight * (gap / 5.0) + 0.20 * min(dependents, 3)
        if r.source == "prerequisite":
            priority += 0.10
        priority = round(min(priority, 1.0), 3)

        reasons = [f"目标要求 {r.required_level} 级，当前 {current} 级，差距 {gap} 级"]
        if r.source == "prerequisite":
            reasons.append("前置技能，影响后续学习")
        if dependents:
            reasons.append(f"是 {dependents} 项目标技能的前置")

        gaps.append(
            SkillGap(
                skill_id=r.skill_id,
                skill_name=r.skill_name,
                current_level=current,
                target_level=r.required_level,
                gap=gap,
                priority=priority,
                reasons=reasons,
            )
        )

    gaps.sort(key=lambda g: (-g.priority, -g.gap, g.skill_id))
    return gaps