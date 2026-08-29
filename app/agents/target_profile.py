"""目标画像构建（方案第 5、6、8 节）：技术需求 / 岗位需求 → TargetProfile。

Agent 职责边界（方案第 15 节）：本层只做「自然语言目标 → 结构化技能需求」并统一到
目标技能画像；技能关系查询走知识层（app/knowledge），不各自维护技能逻辑、不依赖 LLM
猜技能，从根上减少幻觉，保证技能关系来源统一。
"""
from __future__ import annotations

import logging
from typing import Any

from app.config import Config
from app.domain import SkillRequirement, TargetProfile

logger = logging.getLogger(__name__)


def _name_map(config: Config) -> dict[str, str]:
    """技能 id → 名称 映射（JSON/DB 均可用）。"""
    from app.knowledge import list_skills

    return {s["id"]: s["name"] or s["id"] for s in list_skills(config)}


def build_tech_target(config: Config, target_skills: list[dict]) -> TargetProfile:
    """技术学习目标 → TargetProfile。

    以目标技能为核心，用技能关系图谱展开：
    - requires（前置）→ source=prerequisite，必学，权重 0.7；
    - composite_of（子能力）→ source=composite，掌握组合即需具备分部，权重 0.6；
    - related（关联）→ source=related，上下文扩展，权重 0.3。
    ``target_skills`` 形如 ``[{"skill_id","skill_name","level","weight"}]``。
    """
    from app.knowledge import relations

    names = _name_map(config)
    skills: list[SkillRequirement] = []
    seen: set[str] = set()

    def add(skill_id: str, name: str, level: int, weight: float, source: str) -> None:
        if not skill_id or skill_id in seen:
            return
        seen.add(skill_id)
        skills.append(
            SkillRequirement(
                skill_id=skill_id,
                skill_name=name or names.get(skill_id, skill_id),
                required_level=level,
                weight=weight,
                source=source,
            )
        )

    goal_names: list[str] = []
    for t in target_skills:
        sid = str(t.get("skill_id") or "")
        name = str(t.get("skill_name") or names.get(sid, sid))
        goal_names.append(name)
        add(sid, name, int(t.get("level", 3)), float(t.get("weight", 1.0)), "target")
        rel = relations(config, sid)
        for prereq in rel.get("requires", []):
            add(prereq, names.get(prereq, prereq), 2, 0.7, "prerequisite")
        for comp in rel.get("composite_of", []):
            add(comp, names.get(comp, comp), 2, 0.6, "composite")
        for related in rel.get("related", []):
            add(related, names.get(related, related), 2, 0.3, "related")

    # target 在最前，其余按权重降序（前置 > 子能力 > 关联）
    skills.sort(key=lambda s: (s.source != "target", -s.weight))
    return TargetProfile(
        goal_type="tech_learning",
        goal_name=" / ".join(goal_names) or "tech_learning",
        skills=skills,
    )


def build_job_target(config: Config, role_id: str) -> TargetProfile | None:
    """岗位求职目标 → TargetProfile：直接复用岗位能力知识库的 required_skills。"""
    from app.knowledge import get_role

    role = get_role(config, role_id)
    if role is None:
        return None
    return TargetProfile(
        goal_type="job_search",
        goal_name=role.role_name or role_id,
        skills=role.required_skills,
    )


def summarize(target: TargetProfile) -> str:
    """目标画像 → 简洁自然语言摘要（供 reply_node 展示）。"""
    core = ", ".join(f"{s.skill_name}({s.required_level})" for s in target.skills)
    return (
        f"已为你建立目标技能画像「{target.goal_name}」：{core}。"
        "接下来我会通过几个问题了解你当前的技术栈，再计算差距并给出路径。"
    )