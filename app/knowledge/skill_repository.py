"""技能知识库 repository：技能词典 + 技能关系查询（方案第 19 节）。

数据源：PostgreSQL（skill_nodes/skill_edges）优先，无库时降级为 JSON 内存图。
"""
from __future__ import annotations

import logging

from psycopg.rows import dict_row

from app.config import Config
from app.knowledge import _json_source
from app.persistence import db as pgdb

logger = logging.getLogger(__name__)


def _load_graph(config: Config) -> dict:
    """加载统一图谱结构 {nodes: {id:{name,domain}}, edges: [(source,target,rel)]}。

    DB 优先；未配置库或连接失败时降级 JSON。
    """
    if config and getattr(config, "database_url", ""):
        try:
            from app.gap import graph_store

            nodes = graph_store.load_skill_nodes(config)
            with pgdb.connect(config) as conn:
                conn.row_factory = dict_row
                rows = conn.execute("SELECT source, target, rel FROM skill_edges").fetchall()
            edges = [(r["source"], r["target"], r["rel"]) for r in rows]
            return {"nodes": nodes, "edges": edges}
        except Exception:  # noqa: BLE001 - DB 不可用/缺表时降级 JSON
            logger.warning("技能图谱 DB 读取失败，降级 JSON", exc_info=True)

    g = _json_source.load_graph()
    nodes = {k: {"name": v["name"], "domain": v.get("domain")} for k, v in g["nodes"].items()}
    return {"nodes": nodes, "edges": g["edges"]}


def list_skills(config: Config) -> list[dict]:
    """返回全部技能节点 [{id, name, domain}]。"""
    graph = _load_graph(config)
    return [
        {"id": k, "name": v.get("name") or k, "domain": v.get("domain")}
        for k, v in graph["nodes"].items()
    ]


def relations(config: Config, skill_id: str) -> dict:
    """返回某技能的三类关系（邻接技能 id 列表）。

    返回 ``{"requires": [...], "composite_of": [...], "related": [...]}``。
    requires 取「前置技能」（source→target 且 target==skill_id 的 source）。
    """
    graph = _load_graph(config)
    out = {"requires": [], "composite_of": [], "related": []}
    for source, target, rel in graph["edges"]:
        if rel == "requires":
            # 边 B→A 表示 A 需要 B：target 是被依赖技能，source 是它的前置
            if target == skill_id:
                out["requires"].append(source)
        else:
            if source == skill_id:
                out[rel].append(target)
    return out


def prerequisites(config: Config, skill_id: str) -> list[str]:
    """返回技能的直接前置（requires）id 列表，去重。"""
    return list(dict.fromkeys(relations(config, skill_id)["requires"]))


def parent_skills(config: Config, skill_id: str) -> list[str]:
    """返回把该技能作为子能力的「父技能」id 列表（composite_of：父→子）。

    例如 checkpoint / state_management / node_graph_编排 的父技能是 langgraph。
    """
    graph = _load_graph(config)
    parents = [source for source, target, rel in graph["edges"] if rel == "composite_of" and target == skill_id]
    return list(dict.fromkeys(parents))


def resolve_skill(config: Config, name: str) -> dict | None:
    """按技能名（或 id、别名）解析技能节点；未命中返回 None。"""
    key = _json_source.slug(name)
    graph = _load_graph(config)
    if key in graph["nodes"]:
        node = graph["nodes"][key]
        return {"id": key, "name": node.get("name") or name, "domain": node.get("domain")}
    # 名称精确匹配兜底（处理中文名 slug 差异）
    for sid, node in graph["nodes"].items():
        if (node.get("name") or "").lower() == str(name).strip().lower():
            return {"id": sid, "name": node.get("name"), "domain": node.get("domain")}
    return None