"""阶段 7 长期记忆持久化（memory/store）：memories / memory_events / pending_actions（psycopg 直连）。

对齐既有 vectorstore / profile store 风格；不调 LLM。语义向量检索复用 pgvector 余弦相似度。
"""
from __future__ import annotations

import logging
from typing import Any

from pgvector import Vector
from pgvector.psycopg import register_vector
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from app.config import Config
from app.memory.schemas import Episode, MemoryItem, PendingActionRequest
from app.persistence import db as pgdb

logger = logging.getLogger(__name__)

_PENDING_STATUS = {"pending", "approved", "rejected", "expired"}
# API 决策入参（approve/reject）→ 落库状态（approved/rejected）
_DECISION_STATUS = {"approve": "approved", "reject": "rejected"}


def _ensure_vector(conn) -> None:
    register_vector(conn)


# ---------------- memories ----------------

def upsert_memory(config: Config, item: MemoryItem, embedding: list[float] | None) -> str:
    """按 (user_id, namespace, key) 幂等写入；返回 mem_id。"""
    with pgdb.connect(config) as conn:
        if embedding:
            _ensure_vector(conn)
        conn.execute(
            """
            INSERT INTO memories (id, user_id, namespace, key, text, payload, embedding, importance)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (user_id, namespace, key) DO UPDATE SET
              text = EXCLUDED.text,
              payload = EXCLUDED.payload,
              embedding = EXCLUDED.embedding,
              importance = EXCLUDED.importance,
              updated_at = now()
            """,
            (
                item.mem_id,
                item.user_id,
                item.namespace,
                item.key,
                item.text,
                Jsonb(item.payload),
                Vector(embedding) if embedding else None,
                item.importance,
            ),
        )
    return item.mem_id


def get_memory(config: Config, mem_id: str) -> dict[str, Any] | None:
    with pgdb.connect(config) as conn:
        conn.row_factory = dict_row
        row = conn.execute(
            "SELECT * FROM memories WHERE id = %s", (mem_id,)
        ).fetchone()
    return row


def delete_memory(config: Config, mem_id: str) -> bool:
    with pgdb.connect(config) as conn:
        cur = conn.execute("DELETE FROM memories WHERE id = %s", (mem_id,))
    return cur.rowcount > 0


def list_memories(
    config: Config, user_id: str, namespace: str | None = None, limit: int = 50, offset: int = 0
) -> list[dict[str, Any]]:
    where, params = ["user_id = %s"], [user_id]
    if namespace:
        where.append("namespace = %s")
        params.append(namespace)
    params += [limit, offset]
    with pgdb.connect(config) as conn:
        conn.row_factory = dict_row
        rows = conn.execute(
            f"""
            SELECT id, user_id, namespace, key, text, payload, importance, created_at, updated_at
            FROM memories WHERE {' AND '.join(where)}
            ORDER BY updated_at DESC LIMIT %s OFFSET %s
            """,
            params,
        ).fetchall()
    return rows


def search_vector(
    config: Config, user_id: str, query_vec: list[float], top_k: int, namespace: str | None = None
) -> list[dict[str, Any]]:
    """余弦 Top-K 检索（用户隔离，可选命名空间过滤）。"""
    where = ["user_id = %s AND embedding IS NOT NULL"]
    params: list[Any] = [Vector(query_vec), user_id]
    if namespace:
        where.append("namespace = %s")
        params.append(namespace)
    params += [Vector(query_vec), top_k]
    with pgdb.connect(config) as conn:
        _ensure_vector(conn)
        conn.row_factory = dict_row
        rows = conn.execute(
            f"""
            SELECT id, user_id, namespace, key, text, payload,
                   1 - (embedding <=> %s) AS score
            FROM memories
            WHERE {' AND '.join(where)}
            ORDER BY embedding <=> %s
            LIMIT %s
            """,
            params,
        ).fetchall()
    return rows


def search_text(
    config: Config, user_id: str, query: str, top_k: int, namespace: str | None = None
) -> list[dict[str, Any]]:
    """关键词兜底（无向量时按命名空间过滤后做 ILIKE 匹配）。"""
    where = ["user_id = %s"]
    params: list[Any] = [user_id]
    if namespace:
        where.append("namespace = %s")
        params.append(namespace)
    if query:
        where.append("text ILIKE %s OR key ILIKE %s")
        params += [f"%{query}%", f"%{query}%"]
    params += [top_k]
    with pgdb.connect(config) as conn:
        conn.row_factory = dict_row
        rows = conn.execute(
            f"""
            SELECT id, user_id, namespace, key, text, payload, 1.0 AS score
            FROM memories WHERE {' AND '.join(where)}
            ORDER BY importance DESC, updated_at DESC LIMIT %s
            """,
            params,
        ).fetchall()
    return rows


# ---------------- memory_events ----------------

def append_event(config: Config, ep: Episode) -> str:
    with pgdb.connect(config) as conn:
        conn.execute(
            """
            INSERT INTO memory_events (id, user_id, event_type, ref_ids, summary, payload)
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (ep.event_id, ep.user_id, ep.event_type, Jsonb(ep.ref_ids), ep.summary or None, Jsonb(ep.payload)),
        )
    return ep.event_id


def query_events(
    config: Config, user_id: str, event_type: str | None = None, limit: int = 20
) -> list[dict[str, Any]]:
    where, params = ["user_id = %s"], [user_id]
    if event_type:
        where.append("event_type = %s")
        params.append(event_type)
    params += [limit]
    with pgdb.connect(config) as conn:
        conn.row_factory = dict_row
        rows = conn.execute(
            f"""
            SELECT id, user_id, event_type, ref_ids, summary, payload, created_at
            FROM memory_events WHERE {' AND '.join(where)}
            ORDER BY created_at DESC LIMIT %s
            """,
            params,
        ).fetchall()
    return rows


# ---------------- pending_actions ----------------

def create_pending(config: Config, req: PendingActionRequest, pa_id: str) -> str:
    with pgdb.connect(config) as conn:
        conn.execute(
            """
            INSERT INTO pending_actions (id, user_id, action_type, payload, status, summary)
            VALUES (%s, %s, %s, %s, 'pending', %s)
            """,
            (pa_id, req.user_id, req.action_type, Jsonb(req.payload), req.summary or None),
        )
    return pa_id


def list_pending(
    config: Config, user_id: str, status: str | None = None, limit: int = 50
) -> list[dict[str, Any]]:
    where, params = ["user_id = %s"], [user_id]
    if status in _PENDING_STATUS:
        where.append("status = %s")
        params.append(status)
    params += [limit]
    with pgdb.connect(config) as conn:
        conn.row_factory = dict_row
        rows = conn.execute(
            f"""
            SELECT id, user_id, action_type, payload, status, summary, requested_at, decided_at
            FROM pending_actions WHERE {' AND '.join(where)}
            ORDER BY requested_at DESC LIMIT %s
            """,
            params,
        ).fetchall()
    return rows


def expire_pending(config: Config, pa_id: str, expires_seconds: int) -> None:
    """把超过 expires_seconds 仍未决的动作标记为 expired。"""
    with pgdb.connect(config) as conn:
        conn.execute(
            """
            UPDATE pending_actions SET status = 'expired', decided_at = now()
            WHERE id = %s AND status = 'pending'
              AND now() > requested_at + make_interval(secs => %s)
            """,
            (pa_id, expires_seconds),
        )


def decide_pending(config: Config, pa_id: str, decision: str, expires_seconds: int) -> str:
    """对 pending 动作做决策并落库（返回落库状态 approved/rejected）。非法决策抛 ValueError。"""
    status = _DECISION_STATUS.get(decision)
    if status is None:
        raise ValueError(f"非法决策：{decision}")
    expire_pending(config, pa_id, expires_seconds)
    with pgdb.connect(config) as conn:
        conn.row_factory = dict_row
        row = conn.execute(
            "SELECT status FROM pending_actions WHERE id = %s", (pa_id,)
        ).fetchone()
    if row is None:
        raise ValueError("待确认动作不存在或已过期")
    if row["status"] != "pending":
        raise ValueError(f"动作已处置，不可重复决策（当前状态：{row['status']}）")
    with pgdb.connect(config) as conn:
        conn.execute(
            "UPDATE pending_actions SET status = %s, decided_at = now() WHERE id = %s",
            (status, pa_id),
        )
    return status