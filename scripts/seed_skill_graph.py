"""生成技能图种子（阶段 4）：由阶段 2 两份 JSON 生成 skill_nodes/skill_edges/role_skills（幂等 + dry-run）。

用法：
    .venv/bin/python -m scripts.seed_skill_graph                 # 入库（幂等）
    .venv/bin/python -m scripts.seed_skill_graph --dry-run        # 只预览，不写入
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import get_config
from app.persistence import db as pgdb

RELATIONS_JSON = Path(__file__).resolve().parent.parent / "SkillPilot_skill_relations.json"
ROLES_JSON = Path(__file__).resolve().parent.parent / "SkillPilot_role_competencies.json"
IMPLICIT_DESC = "来自关系图隐式节点"


def _slug(name: str) -> str:
    """技能名 → 小写蛇形 id（与 seed_skills._slug 保持一致）。"""
    s = name.strip().lower()
    s = re.sub(r"[/\\()（）](s)?", "_", s)
    s = re.sub(r"[^a-z0-9\u4e00-\u9fff_]+", "_", s)
    return re.sub(r"_+", "_", s).strip("_")


def collect_nodes() -> tuple[dict[str, dict], set[str]]:
    """收集技能节点 {id: {id,name,domain}} 与隐式节点 id 集合。

    显式节点：relations.skills[].skill；隐式节点：仅在 composite_of/requires/related
    中作为引用出现、但不在 relations.skills 列表里的名称（如"编程基础"）。
    """
    nodes: dict[str, dict] = {}
    referenced: set[str] = set()
    rel_data = {}
    if RELATIONS_JSON.exists():
        rel_data = json.loads(RELATIONS_JSON.read_text(encoding="utf-8"))

    for node in rel_data.get("skills", []):
        name = node.get("skill", "").strip()
        if not name:
            continue
        sid = _slug(name)
        nodes[sid] = {"id": sid, "name": name, "domain": node.get("domain"), "implicit": False}
        for field in ("composite_of", "requires", "related"):
            for child in node.get(field, []) or []:
                referenced.add(_slug(str(child).strip()))

    implicit: set[str] = set()
    for rid in referenced - set(nodes):
        # 名称取引用原名（还原）——这里无法还原原文，用 id 作显示名，
        # 稍后在 build 阶段以角色/关系中的原名为准补充到 nodes。
        implicit.add(rid)
    return nodes, implicit


def build(rel_data: dict, roles_data: dict) -> dict:
    """组装三张表的最终内容，供 dry-run / 入库共用。

    返回 {"nodes": [...], "edges": [...], "role_skills": [...]}
    """
    nodes, _implicit_ids = collect_nodes()
    explicit_names = {n["name"]: n for n in nodes.values()}

    def ensure(name: str) -> str:
        """确保技能节点存在（显式或隐式），返回其 id。"""
        nname = str(name).strip()
        sid = _slug(nname)
        if sid not in nodes:
            orig = explicit_names.get(nname, {}).get("name", nname)
            nodes[sid] = {
                "id": sid,
                "name": orig,
                "domain": None,
                "implicit": True,
            }
            explicit_names.setdefault(nname, nodes[sid])
        return sid

    edges: list[dict] = []
    for node in rel_data.get("skills", []):
        skill = node.get("skill", "").strip()
        if not skill:
            continue
        sid = ensure(skill)
        for field, rel in (("requires", "requires"), ("composite_of", "composite_of"), ("related", "related")):
            for child in node.get(field, []) or []:
                cid = ensure(child)
                if rel == "composite_of":
                    # 组合关系：source=父技能, target=子能力
                    edges.append({"source": sid, "target": cid, "rel": rel})
                else:
                    # requires：A 需要 B ⇒ 边 B→A（source=前置, target=技能）
                    # related：source=技能, target=相关技能
                    src, tgt = (cid, sid) if rel == "requires" else (sid, cid)
                    edges.append({"source": src, "target": tgt, "rel": rel})

    role_skills: list[dict] = []
    for role in roles_data.get("roles", []):
        role_id = role.get("role_id", "")
        if not role_id:
            continue
        for req in role.get("required_skills", []):
            name = req.get("skill", "").strip()
            if not name:
                continue
            role_skills.append(
                {
                    "role_id": role_id,
                    "role_name": role.get("role", ""),
                    "category": role.get("category"),
                    "skill_id": ensure(name),
                    "level": req.get("level", 0),
                    "weight": req.get("weight", 1.0),
                    "reason": req.get("reason"),
                }
            )

    # 隐式节点补 description
    for n in nodes.values():
        if n.get("implicit"):
            n["description"] = IMPLICIT_DESC

    return {
        "nodes": sorted(nodes.values(), key=lambda r: r["id"]),
        "edges": sorted(edges, key=lambda r: (r["source"], r["target"], r["rel"])),
        "role_skills": role_skills,
    }


def run(dry_run: bool = False) -> int:
    rel_data = json.loads(RELATIONS_JSON.read_text(encoding="utf-8")) if RELATIONS_JSON.exists() else {}
    roles_data = json.loads(ROLES_JSON.read_text(encoding="utf-8")) if ROLES_JSON.exists() else {}
    data = build(rel_data, roles_data)

    if dry_run:
        print(
            f"[dry-run] 技能节点 {len(data['nodes'])}，边 {len(data['edges'])}，"
            f"岗位技能 {len(data['role_skills'])} 条"
        )
        for n in data["nodes"]:
            print(f"  [node] {n['id']:<30} {n['name']}  (implicit={n.get('implicit', False)})")
        for e in data["edges"][:20]:
            print(f"  [edge] {e['source']} -{e['rel']}-> {e['target']}")
        return len(data["nodes"])

    cfg = get_config()
    if not cfg.database_url:
        raise SystemExit("DATABASE_URL 未配置")

    n, e, rs = 0, 0, 0
    with pgdb.connect(cfg) as conn:
        for node in data["nodes"]:
            cur = conn.execute(
                """
                INSERT INTO skill_nodes (id, name, domain, description)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (id) DO UPDATE SET
                  name = EXCLUDED.name,
                  domain = EXCLUDED.domain,
                  description = EXCLUDED.description
                """,
                (
                    node["id"],
                    node["name"],
                    node.get("domain"),
                    node.get("description"),
                ),
            )
            n += cur.rowcount
        for eo in data["edges"]:
            cur = conn.execute(
                """
                INSERT INTO skill_edges (source, target, rel)
                VALUES (%s, %s, %s)
                ON CONFLICT (source, target, rel) DO NOTHING
                """,
                (eo["source"], eo["target"], eo["rel"]),
            )
            e += cur.rowcount
        for r in data["role_skills"]:
            cur = conn.execute(
                """
                INSERT INTO role_skills (role_id, role_name, category, skill_id, level, weight, reason)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (role_id, skill_id) DO UPDATE SET
                  role_name = EXCLUDED.role_name,
                  category = EXCLUDED.category,
                  level = EXCLUDED.level,
                  weight = EXCLUDED.weight,
                  reason = EXCLUDED.reason
                """,
                (r["role_id"], r["role_name"], r["category"], r["skill_id"], r["level"], r["weight"], r["reason"]),
            )
            rs += cur.rowcount
    print(
        f"已写入/更新 技能节点 {n}，边 {e}，岗位技能 {rs} 条 "
        f"(节点总数 {len(data['nodes'])})"
    )
    return len(data["nodes"])


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="生成技能图种子")
    parser.add_argument("--dry-run", action="store_true", help="只预览不写入")
    args = parser.parse_args()
    run(dry_run=args.dry_run)