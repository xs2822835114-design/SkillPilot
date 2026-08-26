"""POST /api/v1/chat —— 对话 / Agent 编排入口（识别意图并引导到已上线的业务能力）。"""
from __future__ import annotations

from flask import Blueprint, Response, current_app, request, stream_with_context

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
    # 阶段 7：invoke 前注入跨 thread 长期记忆（memory_context），让新会话能读到历史画像/偏好
    memory_context = _load_memory_context(cfg, req.user_id)
    final_state = graph.invoke(
        {
            "user_id": req.user_id,
            "thread_id": req.thread_id,
            "message": req.message,
            "intent_hint": req.intent_hint,
            "memory_context": memory_context,
        },
        config={"configurable": {"thread_id": req.thread_id}},
    )

    # 阶段 7：超长对话触发摘要压缩（best-effort）
    messages = final_state.get("messages") or []
    if messages and len(messages) >= getattr(cfg, "memory_summary_threshold_messages", 20):
        try:
            from app.memory.service import summarize
            from app.memory.schemas import SummarizeRequest

            summarize(cfg, SummarizeRequest(user_id=req.user_id, thread_id=req.thread_id, messages=messages))
        except Exception:  # noqa: BLE001
            current_app.logger.warning("对话摘要压缩失败", exc_info=True)

    return ok_response(_build_result(final_state))


@chat_bp.post("/api/v1/chat/stream")
def chat_stream():
    """阶段 8：SSE 流式对话。meta → delta* → done；失败/关流式时退化为一次性事件。"""
    cfg = current_app.extensions["skillmap"]["config"]
    raw = request.get_json(silent=True)
    if raw is None:
        raise APIError(CODE_JSON_INVALID, "请求体必须为合法 JSON", 400)
    try:
        req = UserRequest.model_validate(raw)
    except Exception as exc:  # noqa: BLE001
        raise APIError(CODE_VALIDATION, first_validation_error(exc), 422)

    from app.agents import streamer

    def generate():
        try:
            yield from streamer.stream_reply(
                cfg, req.user_id, req.thread_id, req.message, req.intent_hint
            )
        except Exception:  # noqa: BLE001 - 流式失败降级为一次性 error 事件，不让前端挂起
            current_app.logger.warning("流式回复异常，降级为 error 事件", exc_info=True)
            import json

            yield f"data: {json.dumps({'type': 'error', 'message': '流式输出异常，请刷新后重试'}, ensure_ascii=False)}\n\n"

    return Response(
        stream_with_context(generate()), content_type="text/event-stream"
    )


@chat_bp.get("/api/v1/chat/stream")
def chat_stream_get():
    """GET 版 SSE 流式：供浏览器 EventSource 原生消费（对 SSE 最稳）。
    参数经 query 传：user_id / thread_id / message / intent_hint。
    """
    cfg = current_app.extensions["skillmap"]["config"]
    user_id = (request.args.get("user_id", "") or "").strip()
    thread_id = (request.args.get("thread_id", "") or "").strip()
    message = request.args.get("message", "") or ""
    intent_hint = request.args.get("intent_hint") or None
    if not (user_id and thread_id and message):
        raise APIError(CODE_VALIDATION, "user_id/thread_id/message 必填", 422)

    from app.agents import streamer

    def generate():
        try:
            yield from streamer.stream_reply(cfg, user_id, thread_id, message, intent_hint)
        except Exception:  # noqa: BLE001 - SSE 异常降级为一次性 error 事件
            current_app.logger.warning("SSE(GET) 流式生成异常", exc_info=True)
            import json

            yield f"data: {json.dumps({'type': 'error', 'message': '流式输出异常，请刷新后重试'}, ensure_ascii=False)}\n\n"

    return Response(
        stream_with_context(generate()), content_type="text/event-stream"
    )


def _load_memory_context(cfg, user_id) -> dict:
    """跨 thread 长期记忆（memory_context）；未启用或异常返回空 dict，不阻断主流程。"""
    try:
        from app.memory.service import recall_for_user

        return recall_for_user(cfg, user_id)
    except Exception:  # noqa: BLE001
        current_app.logger.warning("加载长期记忆失败 user=%s", user_id, exc_info=True)
        return {}


def _build_result(state: dict) -> dict:
    """将最终 State 映射为 /chat 响应 data（WorkflowResult 契约，阶段 9 透传 artifacts/steps）。"""
    intent = state.get("intent") or "chat"
    messages = state.get("messages") or []
    reply = messages[-1]["content"] if messages else ""
    return {
        "route": intent,
        "steps": state.get("steps") or ["intent_recognize", "reply"],
        "reason": f"已识别意图「{intent}」；精细路由（对话/学习计划）",
        "reply": reply,
        "workflow_status": state.get("workflow_status", "done"),
        "artifacts": state.get("artifacts") or {},
        "evidence": [],
    }
