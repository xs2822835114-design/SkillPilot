"""阶段 2 RAG 接口（HTTP 入出；业务在 app/rag 层）。

POST /api/v1/rag/ingest   -- 入库
POST /api/v1/rag/search   -- 检索
POST /api/v1/rag/query    -- RAG 问答（带证据）
"""
from __future__ import annotations

from flask import Blueprint, current_app, request

from app.api.errors import (
    CODE_EMBEDDING,
    CODE_JSON_INVALID,
    CODE_RETRIEVAL,
    CODE_VALIDATION,
    APIError,
    ok_response,
)
from app.api.schemas import first_validation_error
from app.rag import qa_chain, service
from app.rag.schemas import (
    RagError,
    RagIngestRequest,
    RagQueryRequest,
    RagSearchRequest,
)

rag_bp = Blueprint("rag", __name__)


def _config():
    return current_app.extensions["skillmap"]["config"]


def _ensure_kb():
    cfg = _config()
    if not cfg.database_url:
        raise APIError(CODE_RETRIEVAL, "知识库不可用：未配置 DATABASE_URL", 503)


def _validate(raw, model):
    try:
        return model.model_validate(raw)
    except Exception as exc:  # noqa: BLE001
        raise APIError(CODE_VALIDATION, first_validation_error(exc), 422)


@rag_bp.post("/api/v1/rag/ingest")
def rag_ingest():
    raw = request.get_json(silent=True)
    if raw is None:
        raise APIError(CODE_JSON_INVALID, "请求体必须为合法 JSON", 400)
    req = _validate(raw, RagIngestRequest)
    _ensure_kb()
    try:
        result = service.ingest(_config(), req)
    except RagError as e:
        raise APIError(e.code, e.message, 500)
    except ValueError as e:
        raise APIError(CODE_VALIDATION, str(e), 422)
    return ok_response(result.model_dump())


@rag_bp.post("/api/v1/rag/search")
def rag_search():
    raw = request.get_json(silent=True)
    if raw is None:
        raise APIError(CODE_JSON_INVALID, "请求体必须为合法 JSON", 400)
    req = _validate(raw, RagSearchRequest)
    _ensure_kb()
    try:
        result = service.search(_config(), req)
    except RagError as e:
        raise APIError(e.code, e.message, 500)
    return ok_response(result.model_dump())


@rag_bp.post("/api/v1/rag/query")
def rag_query():
    raw = request.get_json(silent=True)
    if raw is None:
        raise APIError(CODE_JSON_INVALID, "请求体必须为合法 JSON", 400)
    req = _validate(raw, RagQueryRequest)
    _ensure_kb()
    try:
        result = qa_chain.answer(_config(), req.query, req.top_k, req.filter)
    except RagError as e:
        raise APIError(e.code, e.message, 500)
    except Exception as exc:  # noqa: BLE001 - 检索失败统一映射，不裸抛
        current_app.logger.exception("RAG query failed")
        raise APIError(CODE_RETRIEVAL, "RAG 问答服务异常", 500)
    return ok_response(result.model_dump())