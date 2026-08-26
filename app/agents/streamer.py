"""阶段 8 SSE 流式 Agent 输出（agents/streamer）。

流程：复用阶段 1 orchestrator 图计算回复（可靠、有规则兜底）→ 以 SSE 事件流式下发。
- 生成器逐个事件 yield，交给路由的 text/event-stream。
- STREAM_ENABLED=false 时一次性吐完整回复；LLM 不可用/异常时同样走整体兜底，保证"流式失败有降级"。
事件序列：meta → delta* → done；(异常) event:error。
"""
from __future__ import annotations

import logging
import time
from typing import Iterator

from app.config import Config

logger = logging.getLogger(__name__)

# 意图 → 引导路由（Demo 形态：Chat 识别 → 引导到对应页面）
_INTENT_ROUTE = {
    "profile_update": "profile",
    "gap_analysis": "gap",
    "plan_generation": "plan",
    "practice": "practice",
    "evaluation": "evaluation",
    "question": "rag",
    "chat": "chat",
}

_CHUNK = 3  # 每次下发的字符数（演示打字机效果）


def stream_reply(
    config: Config, user_id: str, thread_id: str, message: str, intent_hint: str | None
) -> Iterator[str]:
    """产出 SSE 文本行序列（不含重试字段）。"""
    intent, reply = _compute(config, user_id, thread_id, message, intent_hint)
    route = _INTENT_ROUTE.get(intent, "chat")
    yield _sse("meta", {"intent": intent, "route": route, "thread_id": thread_id})

    stream = bool(getattr(config, "stream_enabled", True))
    for seg in _chunks(reply, stream):
        yield _sse("delta", {"text": seg})

    yield _sse("done", {"thread_id": thread_id, "intent": intent, "route": route})


def _compute(config: Config, user_id: str, thread_id: str, message: str, intent_hint: str | None):
    """复用 /chat 的图调用得到意图与回复文本（可靠、规则兜底，杜绝流式中途失败）。"""
    from flask import current_app

    ext = current_app.extensions["skillmap"]
    graph = ext["graph"]
    if graph is None:
        from app.orchestrator.graph import build_graph
        from app.persistence.checkpointer import get_checkpointer

        graph = build_graph(config, checkpointer=get_checkpointer(config))
        ext["graph"] = graph

    from app.memory.service import recall_for_user

    memory_context = recall_for_user(config, user_id)
    state = graph.invoke(
        {
            "user_id": user_id,
            "thread_id": thread_id,
            "message": message,
            "intent_hint": intent_hint,
            "memory_context": memory_context,
        },
        config={"configurable": {"thread_id": thread_id}},
    )
    messages = state.get("messages") or []
    reply = messages[-1]["content"] if messages else ""
    return state.get("intent") or "chat", reply


def _chunks(reply: str, stream: bool) -> Iterator[str]:
    if not reply:
        yield ""
        return
    if not stream:
        yield reply
        return
    for i in range(0, len(reply), _CHUNK):
        yield reply[i : i + _CHUNK]
        time.sleep(0.015)  # 模拟流式节奏；比赛演示可接受


def _sse(event: str, data: dict) -> str:
    import json

    payload = {"type": event, **data}
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"