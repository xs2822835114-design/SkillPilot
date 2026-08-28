"""阶段 7 长期记忆接口（HTTP 入出；业务在 app/memory 层）。

POST /api/v1/memory/remember        -- 写入语义/偏好/摘要事实
POST /api/v1/memory/search          -- 语义/关键词召回
GET  /api/v1/memory                 -- 列出用户记忆
DELETE /api/v1/memory/<mem_id>      -- 删除单条记忆
POST /api/v1/memory/events          -- 沉淀经历 Episode
GET  /api/v1/memory/events          -- 回查经历
POST /api/v1/memory/summarize       -- 长对话摘要压缩
POST /api/v1/memory/pending         -- HITL：暂停守卫操作
GET  /api/v1/memory/pending         -- HITL：待确认列表
POST /api/v1/memory/pending/<pa_id>/confirm  -- HITL：决策
"""
from __future__ import annotations

from flask import Blueprint, current_app, request

from app.api.errors import (
    CODE_JSON_INVALID,
    CODE_MEMORY,
    CODE_MEMORY_NOT_FOUND,
    CODE_VALIDATION,
    APIError,
    ok_response,
)
from app.api.schemas import first_validation_error
from app.memory import service as memory_service
from app.memory.schemas import (
    EpisodeRequest,
    MemoryRememberRequest,
    MemorySearchRequest,
    PendingActionRequest,
    PendingDecisionRequest,
    SummarizeRequest,
)

memory_bp = Blueprint("memory", __name__)


def _config():
    return current_app.extensions["skillmap"]["config"]


def _ensure_db():
    if not _config().database_url:
        raise APIError(CODE_MEMORY, "长期记忆不可用：未配置 DATABASE_URL", 503)


def _validate(raw, model):
    try:
        return model.model_validate(raw)
    except Exception as exc:  # noqa: BLE001
        raise APIError(CODE_VALIDATION, first_validation_error(exc), 422)


def _body():
    raw = request.get_json(silent=True)
    if raw is None:
        raise APIError(CODE_JSON_INVALID, "请求体必须为合法 JSON", 400)
    return raw


# ---------------- memories ----------------

@memory_bp.post("/api/v1/memory/remember")
def memory_remember():
    _ensure_db()
    req = _validate(_body(), MemoryRememberRequest)
    try:
        result = memory_service.remember(_config(), req)
    except ValueError as exc:
        raise APIError(CODE_VALIDATION, str(exc), 422)
    except Exception:  # noqa: BLE001
        current_app.logger.exception("写入长期记忆失败")
        raise APIError(CODE_MEMORY, "写入长期记忆失败", 500)
    return ok_response(result)


@memory_bp.post("/api/v1/memory/search")
def memory_search():
    _ensure_db()
    req = _validate(_body(), MemorySearchRequest)
    try:
        rows = memory_service.search(_config(), req)
    except ValueError as exc:
        raise APIError(CODE_VALIDATION, str(exc), 422)
    except Exception:  # noqa: BLE001
        current_app.logger.exception("召回长期记忆失败")
        raise APIError(CODE_MEMORY, "召回长期记忆失败", 500)
    return ok_response([r.model_dump() for r in rows])


@memory_bp.get("/api/v1/memory")
def memory_list():
    _ensure_db()
    user_id = request.args.get("user_id", "")
    if not user_id:
        raise APIError(CODE_VALIDATION, "user_id 必填", 422)
    ns = request.args.get("namespace")
    limit = request.args.get("limit", type=int) or 100
    items = memory_service.list_memories(_config(), user_id, ns, limit)
    return ok_response([i.model_dump() for i in items])


@memory_bp.delete("/api/v1/memory/<mem_id>")
def memory_delete(mem_id: str):
    _ensure_db()
    if not memory_service.delete_memory(_config(), mem_id):
        raise APIError(CODE_MEMORY_NOT_FOUND, "记忆记录不存在", 404)
    return ok_response({"deleted": True})


# ---------------- events ----------------

@memory_bp.post("/api/v1/memory/events")
def memory_events_create():
    _ensure_db()
    req = _validate(_body(), EpisodeRequest)
    try:
        event_id = memory_service.record_event(_config(), req)
    except ValueError as exc:
        raise APIError(CODE_VALIDATION, str(exc), 422)
    except Exception:  # noqa: BLE001
        current_app.logger.exception("沉淀经历记忆失败")
        raise APIError(CODE_MEMORY, "沉淀经历记忆失败", 500)
    return ok_response({"event_id": event_id})


@memory_bp.get("/api/v1/memory/events")
def memory_events_list():
    _ensure_db()
    user_id = request.args.get("user_id", "")
    if not user_id:
        raise APIError(CODE_VALIDATION, "user_id 必填", 422)
    et = request.args.get("event_type")
    limit = request.args.get("limit", type=int) or 20
    return ok_response(memory_service.query_events(_config(), user_id, et, limit))


# ---------------- summary ----------------

@memory_bp.post("/api/v1/memory/summarize")
def memory_summarize():
    _ensure_db()
    req = _validate(_body(), SummarizeRequest)
    try:
        result = memory_service.summarize(_config(), req)
    except Exception:  # noqa: BLE001
        current_app.logger.exception("对话摘要压缩失败")
        raise APIError(CODE_MEMORY, "对话摘要压缩失败", 500)
    return ok_response(result)


# ---------------- HITL ----------------

@memory_bp.post("/api/v1/memory/pending")
def memory_pending_create():
    _ensure_db()
    req = _validate(_body(), PendingActionRequest)
    try:
        pa_id = memory_service.pending_create(_config(), req)
    except RuntimeError as exc:
        raise APIError(CODE_MEMORY, str(exc), 503)
    return ok_response({"pa_id": pa_id})


@memory_bp.get("/api/v1/memory/pending")
def memory_pending_list():
    _ensure_db()
    user_id = request.args.get("user_id", "")
    if not user_id:
        raise APIError(CODE_VALIDATION, "user_id 必填", 422)
    status = request.args.get("status")
    limit = request.args.get("limit", type=int) or 50
    return ok_response(memory_service.pending_list(_config(), user_id, status, limit))


@memory_bp.post("/api/v1/memory/pending/<pa_id>/confirm")
def memory_pending_confirm(pa_id: str):
    _ensure_db()
    req = _validate(_body(), PendingDecisionRequest)
    try:
        decision = memory_service.pending_confirm(_config(), pa_id, req.decision)
    except ValueError as exc:
        raise APIError(CODE_VALIDATION, str(exc), 422)
    except RuntimeError as exc:
        raise APIError(CODE_MEMORY, str(exc), 503)
    return ok_response({"status": decision})