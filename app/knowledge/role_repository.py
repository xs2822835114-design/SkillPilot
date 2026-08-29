"""岗位知识库 repository：岗位能力定义读写（方案第 19 节）。

岗位数据源以 role_competencies JSON 为权威（含 summary/seniority 完整字段，
role_skills 表未保留这些字段），通过 domain.Role 契约对外暴露。
"""
from __future__ import annotations

from app.config import Config
from app.domain import Role, SkillRequirement
from app.knowledge import _json_source


def _to_role(raw: dict) -> Role:
    reqs = [
        SkillRequirement(
            skill_id=_json_source.slug(r.get("skill", "")),
            skill_name=r.get("skill", ""),
            required_level=int(r.get("level", 0) or 0),
            weight=float(r.get("weight", 1.0) or 1.0),
            reason=r.get("reason"),
            source="role_competencies",
        )
        for r in raw.get("required_skills", []) or []
        if r.get("skill")
    ]
    return Role(
        role_id=raw.get("role_id", ""),
        role_name=raw.get("role", "") or raw.get("role_en", ""),
        category=raw.get("category", ""),
        seniority=raw.get("seniority", ""),
        summary=raw.get("summary", ""),
        required_skills=reqs,
    )


def list_roles(config: Config | None = None) -> list[Role]:
    """返回全部岗位。"""
    return [_to_role(r) for r in _json_source.load_roles()]


def get_role(config: Config | None, role_id: str) -> Role | None:
    """按 role_id 读取岗位；不存在返回 None。"""
    for r in _json_source.load_roles():
        if r.get("role_id") == role_id:
            return _to_role(r)
    return None


def find_role(config: Config | None, query: str) -> Role | None:
    """按岗位名/英文名模糊匹配岗位；未命中返回 None。

    用于 JobRequirementAgent 的自然语言岗位识别。
    """
    q = (query or "").strip().lower()
    if not q:
        return None
    roles = _json_source.load_roles()
    # 1) 精确命中中文名/英文名
    for r in roles:
        if (r.get("role", "") or "").lower() == q or (r.get("role_en", "") or "").lower() == q:
            return _to_role(r)
    # 2) 包含匹配（中文名 / 英文名 / role_id）
    for r in roles:
        hay = " ".join(
            [str(r.get("role", "")), str(r.get("role_en", "")), str(r.get("role_id", ""))]
        ).lower()
        if q in hay:
            return _to_role(r)
    return None