"""GET /health 健康检查（含 DB / LLM 连通性探测）。"""
from __future__ import annotations

from flask import Blueprint, current_app

from app.api.errors import ok_response

health_bp = Blueprint("health", __name__)


@health_bp.get("/health")
def health():
    cfg = current_app.extensions["skillmap"]["config"]

    db_state = _db_state(cfg)
    llm_state = "ok" if cfg.llm_enabled else "disabled"
    status = "up" if db_state in ("ok", "disabled") else "degraded"

    return ok_response(
        {
            "status": status,
            "version": cfg.version,
            "db": db_state,
            "llm": llm_state,
        }
    )


def _db_state(cfg) -> str:
    """未配置 DATABASE_URL → disabled；连通 → ok；否则 down。"""
    if not cfg.database_url:
        return "disabled"
    try:
        from app.persistence import db

        return "ok" if db.ping(cfg) else "down"
    except Exception:  # noqa: BLE001 - 健康检查需兜底
        return "down"
