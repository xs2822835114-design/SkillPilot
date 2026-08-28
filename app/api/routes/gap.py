"""阶段 4 Skill Graph / Gap 接口（HTTP 入出；业务在 app/gap 层）。

POST /api/v1/gap/request  -- 画像 + 目标岗位 → SkillGapReport 列表
"""
from __future__ import annotations

from flask import Blueprint, current_app, request

from app.api.errors import (
    CODE_GAP,
    CODE_JSON_INVALID,
    CODE_VALIDATION,
    APIError,
    ok_response,
)
from app.api.schemas import first_validation_error
from app.gap import gap_agent
from app.gap.schemas import GapAnalysisRequest

gap_bp = Blueprint("gap", __name__)


def _config():
    return current_app.extensions["skillmap"]["config"]


def _ensure_db():
    cfg = _config()
    if not cfg.database_url:
        raise APIError(CODE_GAP, "缺口分析不可用：未配置 DATABASE_URL", 503)


def _validate(raw, model):
    try:
        req = model.model_validate(raw)
    except Exception as exc:  # noqa: BLE001
        raise APIError(CODE_VALIDATION, first_validation_error(exc), 422)
    try:
        req.ensure_target()
    except ValueError as exc:
        raise APIError(CODE_VALIDATION, str(exc), 422)
    return req


@gap_bp.post("/api/v1/gap/request")
def gap_request():
    raw = request.get_json(silent=True)
    if raw is None:
        raise APIError(CODE_JSON_INVALID, "请求体必须为合法 JSON", 400)
    req = _validate(raw, GapAnalysisRequest)
    _ensure_db()
    try:
        resp = gap_agent.analyze(_config(), req)
    except ValueError as exc:
        # 目标岗位不存在等业务校验失败
        raise APIError(CODE_VALIDATION, str(exc), 422)
    except Exception:  # noqa: BLE001
        current_app.logger.exception("Gap 分析失败")
        raise APIError(CODE_GAP, "缺口分析计算失败", 500)
    # 阶段 7：沉淀经历记忆（best-effort）
    if resp.reports:
        r = resp.reports[0]
        from app.memory.service import record_event_best_effort

        record_event_best_effort(
            _config(), req.user_id, "gap_reported",
            ref_ids={"role_id": r.target_role_id},
            summary=f"缺口分析：目标 {r.target_role}，缺口 {len(r.gaps)} 项",
            payload={"gap_total": r.coverage.gap_total if r.coverage else len(r.gaps)},
        )
    return ok_response(resp.model_dump())