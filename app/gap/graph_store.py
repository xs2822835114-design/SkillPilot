"""技能图存储（阶段 4）：读取 skill_nodes / skill_edges / role_skills（psycopg 直连）。"""
from __future__ import annotations

from psycopg.rows import dict_row

from app.config import Config
from app.persistence import db as pgdb

# 技能领域(domain) → 前端稳定分类(category)（图谱节点着色用；数据层权威映射）
DOMAIN_TO_CATEGORY: dict[str, str] = {
    "Language": "dev",
    "Backend": "dev",
    "Frontend": "dev",
    "Engineering": "dev",
    "Quality": "dev",
    "Computer Science": "dev",
    "Math": "dev",
    "AI": "ai",
    "AI/Infra": "ai",
    "AI/Algorithm": "ai",
    "DB": "data",
    "DB/Cache": "data",
    "Data": "data",
    "Data/Infra": "data",
    "BigData": "data",
    "Messaging": "data",
    "DevOps": "infra",
    "Cloud": "infra",
    "Infra": "infra",
    "OS": "infra",
    "Security": "infra",
    "Reliability": "infra",
    "Architecture": "arch",
}
DEFAULT_CATEGORY = "general"


def category_of_domain(domain: str | None) -> str:
    """领域 → 稳定分类；未知/缺失回退 general。"""
    return DOMAIN_TO_CATEGORY.get(domain or "") if domain else DEFAULT_CATEGORY


class RoleRequirement:
    """某个岗位的一项要求技能。"""

    __slots__ = ("skill_id", "name", "required_level", "weight")

    def __init__(self, skill_id: str, name: str, required_level: int, weight: float) -> None:
        self.skill_id = skill_id
        self.name = name or skill_id
        self.required_level = required_level
        self.weight = weight


class LoadedRole:
    """岗位信息 + 其要求技能集合。"""

    __slots__ = ("role_id", "role_name", "category", "requirements")

    def __init__(self, role_id: str, role_name: str, category: str, requirements: list[RoleRequirement]) -> None:
        self.role_id = role_id
        self.role_name = role_name or role_id
        self.category = category or ""
        self.requirements = requirements


def load_role(config: Config, role_id: str) -> LoadedRole | None:
    """按 role_id 读取岗位及其要求技能；不存在返回 None。"""
    with pgdb.connect(config) as conn:
        conn.row_factory = dict_row
        meta = conn.execute(
            "SELECT role_id, role_name, category FROM role_skills WHERE role_id = %s LIMIT 1",
            (role_id,),
        ).fetchone()
        if meta is None:
            return None
        rows = conn.execute(
            """
            SELECT rs.skill_id, COALESCE(sn.name, rs.skill_id) AS name,
                   rs.level, rs.weight
            FROM role_skills rs
            LEFT JOIN skill_nodes sn ON sn.id = rs.skill_id
            WHERE rs.role_id = %s
            ORDER BY rs.weight DESC, rs.level DESC
            """,
            (role_id,),
        ).fetchall()
    requirements = [
        RoleRequirement(r["skill_id"], r["name"], r["level"], r["weight"]) for r in rows
    ]
    return LoadedRole(meta["role_id"], meta["role_name"], meta["category"], requirements)


def list_roles(config: Config) -> list[dict]:
    """读取全部岗位（去重），供校验/展示。"""
    with pgdb.connect(config) as conn:
        conn.row_factory = dict_row
        rows = conn.execute(
            "SELECT role_id, role_name, category FROM role_skills GROUP BY role_id, role_name, category ORDER BY role_id"
        ).fetchall()
    return [dict(r) for r in rows]


def load_requires_edges(config: Config) -> list[tuple[str, str]]:
    """读取全部 requires 有向边。

    语义：requires 边 source=前置技能, target=技能（技能依赖前置）。
    返回 [(source, target), ...]。
    """
    with pgdb.connect(config) as conn:
        conn.row_factory = dict_row
        rows = conn.execute(
            "SELECT source, target FROM skill_edges WHERE rel = 'requires'"
        ).fetchall()
    return [(r["source"], r["target"]) for r in rows]


def load_skill_names(config: Config) -> dict[str, str]:
    """技能 id → 名称 映射（含隐式节点）。"""
    with pgdb.connect(config) as conn:
        conn.row_factory = dict_row
        rows = conn.execute("SELECT id, name FROM skill_nodes").fetchall()
    return {r["id"]: r["name"] or r["id"] for r in rows}


def load_skill_nodes(config: Config) -> dict[str, dict]:
    """技能 id → {name, domain} 映射（含隐式节点，供图谱节点分类）。"""
    with pgdb.connect(config) as conn:
        conn.row_factory = dict_row
        rows = conn.execute("SELECT id, name, domain FROM skill_nodes").fetchall()
    return {
        r["id"]: {
            "name": r["name"] or r["id"],
            "domain": r.get("domain"),
        }
        for r in rows
    }