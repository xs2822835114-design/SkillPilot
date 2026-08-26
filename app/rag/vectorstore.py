"""pgvector 读写：文档存 rag_documents、chunk+向量存 rag_chunks（psycopg 直连，风格对齐 thread_store）。"""
from __future__ import annotations

import logging
from typing import Any

from pgvector import Vector
from pgvector.psycopg import register_vector
from psycopg.types.json import Jsonb
from psycopg.rows import dict_row

from app.config import Config
from app.persistence import db as pgdb

logger = logging.getLogger(__name__)


def _ensure_vector(conn) -> None:
    register_vector(conn)


# ---------------- 文档 ----------------

def find_doc_by_source(config: Config, source: str) -> dict | None:
    if not source:
        return None
    with pgdb.connect(config) as conn:
        conn.row_factory = dict_row
        row = conn.execute(
            "SELECT doc_id, title FROM rag_documents WHERE source = %s LIMIT 1",
            (source,),
        ).fetchone()
    return {"doc_id": row["doc_id"], "title": row["title"]} if row else None


def upsert_document(config: Config, meta: dict[str, Any]) -> str:
    """按 doc_id 插入或更新文档元信息；返回 doc_id。"""
    doc_id = meta["doc_id"]
    with pgdb.connect(config) as conn:
        conn.execute(
            """
            INSERT INTO rag_documents
              (doc_id, title, source, source_type, category, lang, role_target, skill_tags, meta)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (doc_id) DO UPDATE SET
              title = EXCLUDED.title,
              source = EXCLUDED.source,
              source_type = EXCLUDED.source_type,
              category = EXCLUDED.category,
              lang = EXCLUDED.lang,
              role_target = EXCLUDED.role_target,
              skill_tags = EXCLUDED.skill_tags,
              meta = EXCLUDED.meta,
              updated_at = now()
            """,
            (
                doc_id,
                meta.get("title"),
                meta.get("source"),
                meta.get("source_type", "text"),
                meta.get("category"),
                meta.get("lang"),
                meta.get("role_target"),
                meta.get("skill_tags") or None,
                Jsonb(meta.get("meta") or {}),
            ),
        )
    return doc_id


def delete_document(config: Config, doc_id: str) -> None:
    with pgdb.connect(config) as conn:
        conn.execute("DELETE FROM rag_documents WHERE doc_id = %s", (doc_id,))


# ---------------- chunk ----------------

def delete_chunks_by_doc(config: Config, doc_id: str) -> None:
    with pgdb.connect(config) as conn:
        conn.execute("DELETE FROM rag_chunks WHERE doc_id = %s", (doc_id,))


def insert_chunks(config: Config, chunks: list[dict[str, Any]]) -> None:
    """批量写入 chunk（含向量）。chunk: {chunk_id, doc_id, chunk_index, content, token_count, embedding}。"""
    with pgdb.connect(config) as conn:
        _ensure_vector(conn)
        with conn.cursor() as cur:
            for c in chunks:
                cur.execute(
                    """
                    INSERT INTO rag_chunks
                      (chunk_id, doc_id, chunk_index, content, token_count, embedding)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    """,
                    (
                        c["chunk_id"],
                        c["doc_id"],
                        c["chunk_index"],
                        c["content"],
                        c.get("token_count", 0),
                        Vector(c["embedding"]),
                    ),
                )


# ---------------- 检索 ----------------

def search(
    config: Config,
    query_vec: list[float],
    top_k: int,
    rag_filter: dict[str, Any] | None = None,
    columns: str = "c.content",
) -> list[dict[str, Any]]:
    """Top-K 余弦检索；可选 metadata 过滤。返回行（含 score）。"""
    rag_filter = rag_filter or {}
    where: list[str] = ["c.embedding IS NOT NULL"]
    params: list[Any] = []

    if rag_filter.get("category"):
        where.append("d.category = %s")
        params.append(rag_filter["category"])
    if rag_filter.get("source_type"):
        where.append("d.source_type = %s")
        params.append(rag_filter["source_type"])
    if rag_filter.get("doc_id"):
        where.append("c.doc_id = %s")
        params.append(rag_filter["doc_id"])
    if rag_filter.get("role_target"):
        where.append("d.role_target = %s")
        params.append(rag_filter["role_target"])
    if rag_filter.get("skill_tags"):
        where.append("d.skill_tags && %s")
        params.append(rag_filter["skill_tags"])

    params_vec = Vector(query_vec)
    # 占位符顺序：SELECT 相似度(vec) → WHERE filter 参数 → ORDER BY(vec) → LIMIT(top_k)
    params = [params_vec, *params, params_vec, top_k]

    sql = f"""
        SELECT c.chunk_id, c.content,
               d.doc_id, d.title, d.source, d.source_type, d.category, d.role_target,
               1 - (c.embedding <=> %s) AS score
        FROM rag_chunks c
        JOIN rag_documents d ON d.doc_id = c.doc_id
        WHERE {' AND '.join(where)}
        ORDER BY c.embedding <=> %s
        LIMIT %s
    """
    with pgdb.connect(config) as conn:
        _ensure_vector(conn)
        conn.row_factory = dict_row
        rows = conn.execute(sql, params).fetchall()
    return rows