"""推荐引擎（方案第 15、16、20 节）：学习路径排序 + 岗位匹配。

确定性、可重复：学习路径由技能图谱的 requires 拓扑排序得到；岗位匹配按
「已覆盖要求权重占比」打分排序。
"""
from __future__ import annotations

from app.config import Config
from app.domain import UserSkillProfile
from app.gap import closure
from app.knowledge import _json_source, list_roles


def _requires_edges() -> list[tuple[str, str]]:
    g = _json_source.load_graph()
    return [(s, t) for s, t, rel in g["edges"] if rel == "requires"]


def build_learning_path(config: Config, gap_skill_ids: list[str]) -> list[str]:
    """缺口技能 → 学习路径（前置者先，确定性拓扑排序）。

    只对传入的缺口技能集合排序，保证前置技能排在其依赖技能之前。
    """
    ids = list(dict.fromkeys(gap_skill_ids))
    return closure.topo_sort(ids, _requires_edges())


def build_learning_plan(config: Config, gaps: list, path: list[str]) -> list[dict]:
    """缺口技能（按学习路径排序）→ 带学习资源推荐的学习计划条目。

    每个条目：
    ``{skill_id, skill_name, gap, priority, resources: [{title, url, type, category}]}``。
    资源来自学习资源知识库（knowledge_sources JSON），按技能名匹配，缺失时为空列表。
    """
    from app.knowledge import resources_for
    from app.todo.explain import build_steps

    by_id = {g.skill_id: g for g in gaps}
    plan: list[dict] = []
    for sid in path:
        g = by_id.get(sid)
        if g is None:
            continue
        resources = resources_for(config, g.skill_name, limit=3)
        plan.append(
            {
                "skill_id": sid,
                "skill_name": g.skill_name,
                "gap": g.gap,
                "level": (
                    f"L{g.current_level}→L{g.target_level}"
                    if g.current_level is not None
                    else f"L0→L{g.target_level}"
                ),
                "priority": g.priority,
                "steps": build_steps(g.skill_name, g.gap),
                "resources": [
                    {
                        "title": r.get("title", "") or "",
                        "url": r.get("url", "") or "",
                        "type": r.get("type", "") or "",
                        "category": r.get("category", "") or "",
                    }
                    for r in resources
                ],
            }
        )
    return plan


def recommend_roles(config: Config, user: UserSkillProfile, limit: int = 5) -> list[dict]:
    """用户画像 → 匹配度最高的岗位（coverage 为已覆盖要求权重占比）。

    返回 ``[{role_id, role_name, coverage, gap_count, required_total}]``，按 coverage 降序。
    """
    user_level = {s.skill_id: (s.level if s.level is not None else 0) for s in user.skills}

    scored: list[dict] = []
    for role in list_roles(config):
        reqs = role.required_skills
        total_weight = sum(r.weight for r in reqs) or 1.0
        covered_weight = sum(
            r.weight for r in reqs if user_level.get(r.skill_id, 0) >= r.required_level
        )
        gap_count = sum(1 for r in reqs if user_level.get(r.skill_id, 0) < r.required_level)
        scored.append(
            {
                "role_id": role.role_id,
                "role_name": role.role_name,
                "coverage": round(covered_weight / total_weight, 3),
                "gap_count": gap_count,
                "required_total": len(reqs),
            }
        )

    scored.sort(key=lambda r: (-r["coverage"], r["gap_count"], r["role_id"]))
    return scored[:limit]