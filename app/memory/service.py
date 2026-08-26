"""阶段 7 Memory Manager 总入口（memory/service）。

`remember`/`search`/`record_event`/`recall_for_user`/`summarize` 的统一编排：
按命名空间分派到 semantic/procedural/episodic/middleware，统一 `MEMORY_ENABLED` 门控
与"失败不阻断主流程"兜底。`recall_for_user` 供跨 thread 注入 `memory_context`。
"""
from __future__ import annotations

import logging
from typing import Any

from app.config import Config
from app.memory import episodic, procedural, semantic
from app.memory.middleware import hitl, pii, summary
from app.memory.schemas import (
    EpisodeRequest,
    MemoryItem,
    MemoryRememberRequest,
    MemorySearchRequest,
    MemorySearchResult,
    PendingActionRequest,
    SummarizeRequest,
)

logger = logging.getLogger(__name__)


def enabled(config: Config) -> bool:
    return getattr(config, "memory_enabled", True)


def remember(config: Config, req: MemoryRememberRequest) -> dict[str, Any]:
    """写入一条记忆；返回 {mem_id, pii_redacted, vectorized}。memory 关闭时短路。"""
    if not enabled(config):
        return {"mem_id": "", "pii_redacted": False, "vectorized": False}
    text, hits = pii.scrub(config, req.text)
    payload = pii.mask_payload(config, req.payload) if hits else req.payload
    item = semantic.remember(
        config, req.model_copy(update={"text": text, "payload": payload})
    )
    return {
        "mem_id": item.mem_id,
        "pii_redacted": bool(hits),
        "vectorized": bool(item.text and getattr(config, "memory_embed_enabled", True)),
    }


def search(config: Config, req: MemorySearchRequest) -> list[MemorySearchResult]:
    if not enabled(config):
        return []
    return semantic.search(config, req, getattr(config, "memory_top_k", 5))


def list_memories(config: Config, user_id: str, namespace: str | None, limit: int = 100) -> list[MemoryItem]:
    if not enabled(config):
        return []
    return semantic.list_for_user(config, user_id, namespace, limit)


def delete_memory(config: Config, mem_id: str) -> bool:
    return semantic.remove(config, mem_id)


def record_event(config: Config, req: EpisodeRequest) -> str:
    """best-effort 沉淀经历记忆；非法类型抛 ValueError，其余异常吞掉不阻断。"""
    if not enabled(config):
        return ""
    try:
        summary_text, hits = pii.scrub(config, req.summary)
        payload = pii.mask_payload(config, req.payload) if hits else req.payload
        return episodic.record(
            config, req.model_copy(update={"summary": summary_text, "payload": payload})
        )
    except ValueError:
        raise
    except Exception:  # noqa: BLE001 - 记忆失败不阻断主流程
        logger.warning("记录经历记忆失败 user=%s type=%s", req.user_id, req.event_type, exc_info=True)
        return ""


def record_event_best_effort(
    config: Config, user_id: str, event_type: str, ref_ids: dict | None = None,
    summary: str = "", payload: dict | None = None,
) -> str:
    """供业务路由成功后调用：即使事件类型非法/记忆关闭也绝不抛错。返回事件 id 或空串。"""
    try:
        return record_event(
            config,
            EpisodeRequest(
                user_id=user_id, event_type=event_type,
                ref_ids=ref_ids or {}, summary=summary or "", payload=payload or {},
            ),
        )
    except Exception:  # noqa: BLE001 - 阶段3~6成功副产物，绝不回滚主流程
        logger.warning("Episodic 记忆极简写入失败（已忽略） user=%s type=%s", user_id, event_type)
        return ""


def query_events(config: Config, user_id: str, event_type: str | None = None, limit: int = 20) -> list[dict]:
    if not enabled(config):
        return []
    return episodic.query(config, user_id, event_type, limit)


def recall_for_user(config: Config, user_id: str) -> dict[str, Any]:
    """跨 thread 记忆快照（供 invoke 前注入 `memory_context`）。memory 关闭返回空。"""
    if not enabled(config):
        return {}
    semantic_items = semantic.list_for_user(config, user_id, None, limit=getattr(config, "memory_top_k", 10) * 2)
    summaries = [it for it in semantic_items if it.namespace == "summary"]
    return {
        "semantic": [
            {"key": it.key, "text": it.text, "namespace": it.namespace} for it in semantic_items
        ],
        "preferences": procedural.all_preferences(config, user_id),
        # 最近的对话摘要（计划契约 memory_context.message_summary，用于超长上下文优先注入）
        "message_summary": summaries[0].text if summaries else None,
        "episodic_latest": [e.get("event_type") for e in episodic.query(config, user_id, limit=3)],
    }


def summarize(config: Config, req: SummarizeRequest) -> dict[str, Any]:
    """长对话压缩：超过阈值则生成摘要落库。memory 关闭或未达阈值返回空结果。"""
    if not enabled(config):
        return {"summary": "", "stored": False, "is_llm_enhanced": False}
    s, enhanced = summary.summarize(config, req.user_id, req.thread_id, req.messages)
    return {"summary": s, "stored": bool(s), "is_llm_enhanced": enhanced}


def pending_create(config: Config, req: PendingActionRequest) -> str:
    if not hitl.enabled(config):
        raise RuntimeError("HITL 未启用")
    return hitl.park(config, req)


def pending_list(config: Config, user_id: str, status: str | None = None, limit: int = 50) -> list[dict]:
    if not enabled(config):
        return []
    return hitl.list_pending(config, user_id, status, limit)


def pending_confirm(config: Config, pa_id: str, decision: str) -> str:
    if not hitl.enabled(config):
        raise RuntimeError("HITL 未启用")
    return hitl.confirm(config, pa_id, decision)