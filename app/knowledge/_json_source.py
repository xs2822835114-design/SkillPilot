"""知识层 JSON 数据源：在无 PostgreSQL 时从三份 JSON 加载知识库。

本模块是 JSON 权威解析入口，slug 与节点/边组装逻辑与 scripts/seed_skill_graph.py 保持一致，
保证「DB（由 seed 灌入）路径」与「JSON 降级路径」产出的技能 id / 关系语义完全一致。
"""
from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
RELATIONS_JSON = ROOT / "SkillPilot_skill_relations.json"
ROLES_JSON = ROOT / "SkillPilot_role_competencies.json"
SOURCES_JSON = ROOT / "SkillPilot_knowledge_sources.json"


def slug(name: str) -> str:
    """技能名 → 小写蛇形 id（与 seed_skill_graph._slug 完全一致）。

    斜杠后不再消费字母 s（旧实现 ``(s)?`` 会把 'Java/Scala' 误写成 'java_cala'）。
    """
    s = str(name).strip().lower()
    s = re.sub(r"[/\\()（）]", "_", s)
    s = re.sub(r"[^a-z0-9\u4e00-\u9fff_]+", "_", s)
    return re.sub(r"_+", "_", s).strip("_")


@lru_cache(maxsize=1)
def _read_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


@lru_cache(maxsize=1)
def load_graph() -> dict:
    """解析技能关系 JSON 为内存图谱。

    返回 ``{"nodes": {id: {"name", "domain"}}, "edges": [(source, target, rel)]}``。
    边语义与 seed 一致：requires 为 B→A（source=前置，target=技能），
    composite_of 为 父→子，related 为 技能→相关。
    """
    rel = _read_json(RELATIONS_JSON)
    nodes: dict[str, dict] = {}
    edges: list[tuple[str, str, str]] = []

    def ensure(name: str, domain_hint: str | None = None) -> str:
        sid = slug(name)
        if sid not in nodes:
            nodes[sid] = {"name": str(name).strip(), "domain": domain_hint}
        elif domain_hint and not nodes[sid].get("domain"):
            nodes[sid]["domain"] = domain_hint
        return sid

    for node in rel.get("skills", []):
        skill = str(node.get("skill") or "").strip()
        if not skill:
            continue
        sid = ensure(skill, domain_hint=node.get("domain"))
        parent_domain = nodes[sid].get("domain")
        for field, relname in (
            ("requires", "requires"),
            ("composite_of", "composite_of"),
            ("related", "related"),
        ):
            for child in node.get(field, []) or []:
                cid = ensure(str(child).strip(), domain_hint=parent_domain)
                if relname == "composite_of":
                    edges.append((sid, cid, relname))
                elif relname == "requires":
                    edges.append((cid, sid, relname))
                else:
                    edges.append((sid, cid, relname))

    return {"nodes": nodes, "edges": edges}


@lru_cache(maxsize=1)
def load_roles() -> list[dict]:
    """返回岗位能力 JSON 的原始 roles 列表（含 summary/seniority 等完整字段）。"""
    data = _read_json(ROLES_JSON)
    return data.get("roles", [])


@lru_cache(maxsize=1)
def load_sources() -> list[dict]:
    """返回学习资源 JSON 的原始 sources 列表。"""
    data = _read_json(SOURCES_JSON)
    return data.get("sources", [])