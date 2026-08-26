"""RAG 服务编排：把 loader → splitter → embedding → vectorstore 串起来。

供 API 层调用，不在路由里写业务细节。
"""
from __future__ import annotations

import logging
import uuid

from app.config import Config
from app.rag import loader, retriever, splitter, vectorstore
from app.rag.embeddings import EmbeddingClient
from app.rag.schemas import (
    MAX_DOC_TEXT,
    RagFilter,
    RagIngestRequest,
    RagIngestResponse,
    RagSearchRequest,
    RagSearchResponse,
)

logger = logging.getLogger(__name__)

_DOC_PREFIX = "DOC_"
_CHUNK_PREFIX = "CHK_"


def _new_id(prefix: str) -> str:
    return f"{prefix}{uuid.uuid4().hex[:12]}"


def ingest(config: Config, req: RagIngestRequest) -> RagIngestResponse:
    result = loader.load(req)
    if len(result.text) > MAX_DOC_TEXT:
        raise ValueError(f"文本过长（>{MAX_DOC_TEXT} 字符）")

    # 幂等：同一 source 复用 doc_id
    existing = vectorstore.find_doc_by_source(config, result.source)
    doc_id = existing["doc_id"] if existing else _new_id(_DOC_PREFIX)

    texts = splitter.split(config, result.text)
    embeddings = EmbeddingClient(config).embed(texts)

    vectorstore.upsert_document(
        config,
        {
            "doc_id": doc_id,
            "title": req.title or result.title or result.source,
            "source": result.source,
            "source_type": result.source_type,
            "category": req.category,
            "lang": req.lang,
            "role_target": req.role_target,
            "skill_tags": req.skill_tags,
            "meta": req.meta,
        },
    )
    # 替换式：先清旧 chunk 再写入，避免同源重复
    vectorstore.delete_chunks_by_doc(config, doc_id)
    chunks = [
        {
            "chunk_id": _new_id(_CHUNK_PREFIX),
            "doc_id": doc_id,
            "chunk_index": i,
            "content": t,
            "token_count": splitter.estimate_tokens(t),
            "embedding": embeddings[i],
        }
        for i, t in enumerate(texts)
    ]
    if chunks:
        vectorstore.insert_chunks(config, chunks)

    return RagIngestResponse(doc_id=doc_id, num_chunks=len(chunks))


def search(config: Config, req: RagSearchRequest) -> RagSearchResponse:
    items = retriever.retrieve(config, req.query, req.top_k, _filter_or_none(req))
    return RagSearchResponse(results=items)


def _filter_or_none(req: RagSearchRequest) -> RagFilter | None:
    f = req.filter
    if not (f.category or f.source_type or f.doc_id or f.skill_tags or f.role_target):
        return None
    return f