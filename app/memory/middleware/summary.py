"""阶段 7 摘要中间件（memory/middleware/summary）：超长对话上下文压缩。

消息轮数 >= MEMORY_SUMMARY_THRESHOLD_MESSAGES 时生成摘要（LLM 润色 + 模板兜底），
写入 namespace='summary' 并沉淀一条 conversation_summary Episode；供跨会话优先注入。
不裁剪 Checkpointer 历史（保留既有单会话恢复能力）。
"""
from __future__ import annotations

import logging
import uuid

from app.config import Config
from app.memory import semantic, store
from app.memory.schemas import Episode, MemoryRememberRequest

logger = logging.getLogger(__name__)

_ROLE = {"user": "用户", "assistant": "助手", "system": "系统"}


def should_summarize(config: Config, messages: list[dict]) -> bool:
    if not messages:
        return False
    return len(messages) >= getattr(config, "memory_summary_threshold_messages", 20)


def summarize(config: Config, user_id: str, thread_id: str, messages: list[dict]) -> tuple[str, bool]:
    """生成摘要并落库（summary 记忆 + conversation_summary Episode）。返回 (summary, is_llm_enhanced)。"""
    if not should_summarize(config, messages):
        return "", False
    polished = llm_polish(config, messages)
    summary = polished or _rule_summary(messages)
    is_llm_enhanced = polished is not None

    semantic.remember(
        config,
        MemoryRememberRequest(
            user_id=user_id,
            namespace="summary",
            key=f"thread:{thread_id}",
            text=summary,
            payload={"message_count": len(messages)},
            importance=0.6,
        ),
    )
    store.append_event(
        config,
        Episode(
            event_id=f"EVT_{uuid.uuid4().hex[:12]}",
            user_id=user_id,
            event_type="conversation_summary",
            ref_ids={"thread_id": thread_id},
            summary=summary,
            payload={"message_count": len(messages), "is_llm_enhanced": is_llm_enhanced},
        ),
    )
    return summary, is_llm_enhanced


def llm_polish(config: Config, messages: list[dict]) -> str | None:
    """用 LLM 把对话压成摘要；未启用或失败返回 None 走模板。"""
    try:
        if not getattr(config, "memory_summary_llm_enabled", True) or not config.llm_enabled:
            return None
        from langchain_core.prompts import ChatPromptTemplate
        from langchain_openai import ChatOpenAI

        body = "\n".join(
            f"{_ROLE.get(m.get('role','?'),'?')}: {str(m.get('content',''))[:200]}"
            for m in messages[-20:]
        )
        llm = ChatOpenAI(model=config.llm_model, base_url=config.llm_base_url, api_key=config.llm_api_key, temperature=0)
        prompt = ChatPromptTemplate.from_messages(
            [
                ("system", "你是长期记忆助理。把对话压缩成 ≤120 字的中文摘要，保留用户的技能、目标、关键决策与进展。只输出摘要。"),
                ("human", "{body}"),
            ]
        )
        resp = (prompt | llm).invoke({"body": body})
        text = (resp.content if hasattr(resp, "content") else str(resp)).strip()
        return text or None
    except Exception:  # noqa: BLE001
        logger.warning("摘要 LLM 润色失败，走模板兜底", exc_info=True)
        return None


def _rule_summary(messages: list[dict]) -> str:
    """模板兜底：开头 + 最近轮次的关键内容摘要。"""
    first = next((m for m in messages if m.get("role") == "user"), None)
    head = ""
    if first:
        head = f"开头（用户）：「{str(first.get('content',''))[:40]}」"
    tail = [str(m.get('content', ''))[:80] for m in messages[-4:]]
    return f"对话共 {len(messages)} 条。{head} 最近要点：{'；'.join(tail)}"


def recall_summary(config: Config, user_id: str, thread_id: str) -> str | None:
    """读取某会话的已有摘要（若此前压缩过）。"""
    items = semantic.list_for_user(config, user_id, "summary")
    for it in items:
        if it.key == f"thread:{thread_id}":
            return it.text
    return None