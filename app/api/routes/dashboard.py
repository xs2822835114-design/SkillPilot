"""阶段 8 Dashboard 聚合接口（HTTP；业务在 app/dashboard）。

GET /api/v1/dashboard/<user_id> -- 概览 + 成长报告聚合。
"""
from __future__ import annotations

import re

from flask import Blueprint, current_app, request

from app.api.errors import CODE_DEMO, CODE_VALIDATION, APIError, ok_response
from app.dashboard import service as dashboard_service

dashboard_bp = Blueprint("dashboard", __name__)


def _config():
    return current_app.extensions["skillmap"]["config"]


def _ensure_db():
    if not _config().database_url:
        raise APIError(CODE_DEMO, "Dashboard 不可用：未配置 DATABASE_URL", 503)


@dashboard_bp.get("/api/v1/dashboard/<user_id>")
def dashboard_get(user_id: str):
    uid = (user_id or "").strip()
    if not uid or not re.match(r"^[A-Za-z0-9_-]{1,64}$", uid):
        raise APIError(CODE_VALIDATION, "user_id 非法", 422)
    _ensure_db()
    try:
        dto = dashboard_service.build(_config(), uid)
    except Exception:  # noqa: BLE001
        current_app.logger.exception("Dashboard 聚合失败 user=%s", uid)
        raise APIError(CODE_DEMO, "Dashboard 聚合失败", 500)
    return ok_response(dto.model_dump(mode="json"))