"""阶段 7 语义记忆（memory/semantic）：事实写入 + 召回 + 检索。

写入时若开启 MEMORY_EMBED_ENABLED 则调用阶段 2 EmbeddingClient 向量化；否则 embedding 置 NULL，
召回退化到关键词匹配兜底。不感知 HTTP。
"""
from __future__ import annotations

import logging
import uuid

from app.config import Config
from app.memory import store
from app.memory.schemas import MemoryItem, MemoryRememberRequest, MemorySearchRequest, MemorySearchResult

logger = logging.getLogger(__name__)


def _new_id() -> str:
    return f"MEM_{uuid.uuid4().hex[:12]}"


def _embed(config: Config, text: str) -> list[float] | None:
    """语义向量化；未开启 embedding 或文本为空时返回 None（写 NULL 向量走文本匹配兜底）。"""
    if not getattr(config, "memory_embed_enabled", True):
        return None
    if not text:
        return None
    try:
        from app.rag.embeddings import EmbeddingClient

        return EmbeddingClient(config).embed([text])[0]
    except Exception:  # noqa: BLE001 - 向量化失败写 NULL，走文本兜底，不阻断
        logger.warning("语义记忆向量化失败，写 NULL 向量", exc_info=True)
        return None


def remember(config: Config, req: MemoryRememberRequest) -> MemoryItem:
    """写入一条语义/偏好/摘要记忆（幂等按键覆盖）。"""
    ns = req.ensure_namespace()
    text = (req.text or "").strip()
    embedding = _embed(config, text)
    item = MemoryItem(
        mem_id=_new_id(),
        user_id=req.user_id,
        namespace=ns,
        key=req.key,
        text=text,
        payload=req.payload,
        importance=req.importance,
    )
    store.upsert_memory(config, item, embedding)
    return item


def search(config: Config, req: MemorySearchRequest, default_top_k: int) -> list[MemorySearchResult]:
    """语义检索：向量优先，关键词兜底。无 query 时退化为列出。"""
    ns = req.namespace
    if ns and ns not in ("semantic", "procedural", "summary"):
        raise ValueError(f"非法命名空间：{ns}")
    top_k = req.effective_top_k(default_top_k)
    rows: list[dict] = []
    if req.query:
        embedding = _embed(config, req.query)
        if embedding and getattr(config, "memory_embed_enabled", True):
            rows = store.search_vector(config, req.user_id, embedding, top_k, ns)
        else:
            rows = store.search_text(config, req.user_id, req.query, top_k, ns)
    else:
        rows = store.list_memories(config, req.user_id, ns, limit=top_k)
    return [_row_to_result(r) for r in rows]


def list_for_user(config: Config, user_id: str, namespace: str | None, limit: int = 100) -> list[MemoryItem]:
    """供跨 thread 注入的记忆快照（最新优先）。"""
    rows = store.list_memories(config, user_id, namespace, limit=limit)
    return [_row_to_item(r) for r in rows]


def _row_to_item(r: dict) -> MemoryItem:
    return MemoryItem(
        mem_id=r["id"],
        user_id=r["user_id"],
        namespace=r["namespace"],
        key=r["key"],
        text=r["text"] or "",
        payload=dict(r["payload"] or {}),
        importance=float(r.get("importance") or 0.0),
        created_at=r.get("created_at"),
        updated_at=r.get("updated_at"),
    )


def _row_to_result(r: dict) -> MemorySearchResult:
    return MemorySearchResult(
        mem_id=r["id"],
        key=r["key"],
        text=r["text"] or "",
        namespace=r["namespace"],
        payload=dict(r.get("payload") or {}),
        score=float(r.get("score") or 0.0),
    )


def remove(config: Config, mem_id: str) -> bool:
    return store.delete_memory(config, mem_id)