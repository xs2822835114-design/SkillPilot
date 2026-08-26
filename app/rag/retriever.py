"""Retriever：把 query 转向量 → vectorstore.search → Evidence 列表。"""
from __future__ import annotations

from app.config import Config
from app.rag import vectorstore
from app.rag.embeddings import EmbeddingClient
from app.rag.schemas import EvidenceItem, RagFilter


def retrieve(
    config: Config,
    query: str,
    top_k: int,
    rag_filter: RagFilter | None = None,
) -> list[EvidenceItem]:
    vec = EmbeddingClient(config).embed([query])[0]
    rows = vectorstore.search(config, vec, top_k, rag_filter.model_dump() if rag_filter else None)
    return [_to_evidence(r) for r in rows]


def _to_evidence(row: dict) -> EvidenceItem:
    return EvidenceItem(
        chunk_id=row["chunk_id"],
        doc_id=row["doc_id"],
        title=row.get("title"),
        source=row.get("source"),
        url=row.get("source") if row.get("source_type") == "url" else None,
        source_type=row.get("source_type"),
        category=row.get("category"),
        role_target=row.get("role_target"),
        content=row["content"],
        score=row.get("score"),
        content_preview=row["content"][:200],
    )