"""阶段 8 Skill Graph 读取接口（HTTP；业务在 gap/graph_store）。

GET /api/v1/graph -- 返回全量技能图谱 { nodes, edges }，供前端 SVG 可视化。
"""
from __future__ import annotations

from flask import Blueprint, current_app

from app.api.errors import CODE_DEMO, APIError, ok_response

graph_bp = Blueprint("graph", __name__)


def _config():
    return current_app.extensions["skillmap"]["config"]


def _ensure_db():
    if not _config().database_url:
        raise APIError(CODE_DEMO, "技能图谱不可用：未配置 DATABASE_URL", 503)


@graph_bp.get("/api/v1/graph")
def graph_get():
    _ensure_db()
    try:
        from app.gap import graph_store

        cfg = _config()
        meta = graph_store.load_skill_nodes(cfg)
        edges = graph_store.load_requires_edges(cfg)

        nodes = [
            {
                "id": sid,
                "name": meta[sid]["name"],
                "category": _category(sid, meta[sid].get("domain")),
            }
            for sid in meta
        ]
        return ok_response(
            {
                "nodes": nodes,
                "edges": [{"source": s, "target": t} for s, t in edges],
            }
        )
    except Exception:  # noqa: BLE001
        current_app.logger.exception("读取技能图谱失败")
        raise APIError(CODE_DEMO, "读取技能图谱失败", 500)


def _category(skill_id: str, domain: str | None = None) -> str:
    """节点分类：优先用数据层的领域(domain)；缺失时按 id 关键字近似归堆。

    仅用于布局着色；分类权威映射见 graph_store.DOMAIN_TO_CATEGORY。
    """
    from app.gap import graph_store

    cat = graph_store.category_of_domain(domain)
    if cat != graph_store.DEFAULT_CATEGORY:
        return cat
    sid = (skill_id or "").lower()
    if any(k in sid for k in ("sql", "database", "db", "postgres")):
        return "data"
    if any(k in sid for k in ("python", "code", "java", "node", "api", "web")):
        return "dev"
    if any(k in sid for k in ("rag", "llm", "agent", "nlp", "ml")):
        return "ai"
    if any(k in sid for k in ("cloud", "docker", "k8s", "cid", "devops")):
        return "infra"
    return graph_store.DEFAULT_CATEGORY