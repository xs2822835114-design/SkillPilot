"""阶段 9 reply_node：统一拼接最终回复文本并透传 artifacts（多 Agent 路由的汇合点）。

职责：
- 追加 user / assistant 消息（Checkpointer 持久化）；
- 依据 intent / summary / error / need_input 组装最终回复；
- 组装 steps 与 artifacts，设置 workflow_status。
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

DEFAULT_FALLBACK = "我收到你的消息了，但暂时没能完成处理，请稍后再试。"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def reply_node(state: dict) -> dict[str, Any]:
    history = list(state.get("messages") or [])
    message = (state.get("message") or "").strip()
    intent = state.get("intent") or "chat"
    error = state.get("error") or {}
    summary = state.get("summary") or ""

    # 最终回复：追问 > 业务摘要 > 兜底
    if error.get("type") == "need_input":
        reply = error.get("message") or DEFAULT_FALLBACK
    elif error:
        reply = error.get("message") or DEFAULT_FALLBACK
    else:
        reply = summary or DEFAULT_FALLBACK

    user_msg = {
        "role": "user",
        "content": message,
        "intent_hint": state.get("intent_hint"),
        "created_at": _now_iso(),
    }
    assistant_msg = {
        "role": "assistant",
        "content": reply,
        "intent": intent,
        "created_at": _now_iso(),
    }

    steps = list(state.get("steps") or ["intent_recognize"])
    agent = state.get("current_agent")
    if agent and agent not in steps and agent != "orchestrator_agent":
        steps.append(agent)
    if "reply" not in steps:
        steps.append("reply")

    # 终态归一：chat 无业务节点，pending（orchestrator 的中间态）统一收口为 done
    status = state.get("workflow_status") or "done"
    if intent == "chat" or status == "pending":
        status = "done"

    return {
        "messages": history + [user_msg, assistant_msg],
        "steps": steps,
        "intent": intent,
        "current_agent": agent or "reply",
        "workflow_status": status,
        "artifacts": state.get("artifacts") or {},
        "error": None,
    }
