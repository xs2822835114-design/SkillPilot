"""阶段 7 程序性记忆（memory/procedural）：学习偏好长期读写。

复用阶段 3 `user_preferences`（user_id,key,value JSONB）为唯一权威存储，避免与业务表重复。
负责任的 key：learning_style / available_hours / long_term_goal 等。读写 best-effort。
"""
from __future__ import annotations

import logging
from typing import Any

from app.config import Config
from app.persistence import db as pgdb
from psycopg.types.json import Jsonb

logger = logging.getLogger(__name__)


def get_preference(config: Config, user_id: str, key: str) -> Any | None:
    try:
        with pgdb.connect(config) as conn:
            row = conn.execute(
                "SELECT value FROM user_preferences WHERE user_id = %s AND key = %s",
                (user_id, key),
            ).fetchone()
        return row[0] if row else None
    except Exception:  # noqa: BLE001 - best-effort
        logger.warning("读取偏好失败 key=%s user=%s", key, user_id, exc_info=True)
        return None


def set_preference(config: Config, user_id: str, key: str, value: Any) -> None:
    try:
        with pgdb.connect(config) as conn:
            conn.execute(
                """
                INSERT INTO user_preferences (user_id, key, value, updated_at)
                VALUES (%s, %s, %s, now())
                ON CONFLICT (user_id, key) DO UPDATE SET value = EXCLUDED.value, updated_at = now()
                """,
                (user_id, key, Jsonb(value)),
            )
    except Exception:  # noqa: BLE001 - best-effort
        logger.warning("写入偏好失败 key=%s user=%s", key, user_id, exc_info=True)


def all_preferences(config: Config, user_id: str) -> dict[str, Any]:
    """读取该用户全部学习偏好（供跨 thread 注入）。"""
    try:
        with pgdb.connect(config) as conn:
            rows = conn.execute(
                "SELECT key, value FROM user_preferences WHERE user_id = %s AND value IS NOT NULL",
                (user_id,),
            ).fetchall()
        return {r[0]: r[1] for r in rows}
    except Exception:  # noqa: BLE001
        logger.warning("读取全部偏好失败 user=%s", user_id, exc_info=True)
        return {}