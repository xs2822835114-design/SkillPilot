"""POST /api/v1/chat —— 对话 / Agent 编排入口（阶段 1：单 Agent 最小闭环）。"""
from __future__ import annotations

from flask import Blueprint, current_app, request

from app.api.errors import APIError, CODE_JSON_INVALID, CODE_VALIDATION, ok_response
from app.api.schemas import first_validation_error, UserRequest
from app.persistence import thread_store

chat_bp = Blueprint("chat", __name__)


def _get_graph():
    """惰性构建并缓存编排图（每个应用实例一份，含 checkpointer）。"""
    ext = current_app.extensions["skillmap"]
    if ext["graph"] is None:
        from app.orchestrator.graph import build_graph
        from app.persistence.checkpointer import get_checkpointer

        ext["graph"] = build_graph(ext["config"], checkpointer=get_checkpointer(ext["config"]))
    return ext["graph"]


@chat_bp.post("/api/v1/chat")
def chat():
    cfg = current_app.extensions["skillmap"]["config"]

    raw = request.get_json(silent=True)
    if raw is None:
        raise APIError(CODE_JSON_INVALID, "请求体必须为合法 JSON", 400)

    try:
        req = UserRequest.model_validate(raw)
    except Exception as exc:  # noqa: BLE001 - Pydantic 校验失败统一映射为 422
        raise APIError(CODE_VALIDATION, first_validation_error(exc), 422)

    # 会话元信息落库（best-effort，失败仅告警不阻断）
    thread_store.upsert_thread(cfg, req.thread_id, req.user_id)

    graph = _get_graph()
    final_state = graph.invoke(
        {
            "user_id": req.user_id,
            "thread_id": req.thread_id,
            "message": req.message,
            "intent_hint": req.intent_hint,
        },
        config={"configurable": {"thread_id": req.thread_id}},
    )

    return ok_response(_build_result(final_state))


def _build_result(state: dict) -> dict:
    """将最终 State 映射为 /chat 响应 data（WorkflowResult 契约）。"""
    intent = state.get("intent") or "chat"
    messages = state.get("messages") or []
    reply = messages[-1]["content"] if messages else ""
    return {
        "route": "chat",  # 阶段 1 业务 Agent 未接入，统一走 chat
        "steps": ["intent_recognize", "reply"],
        "reason": f"已识别意图「{intent}」；阶段 1 为单 Agent 最小闭环，业务 Agent（阶段 3~6）尚未接入",
        "reply": reply,
        "workflow_status": state.get("workflow_status", "done"),
        "artifacts": {},
        "evidence": [],
    }
