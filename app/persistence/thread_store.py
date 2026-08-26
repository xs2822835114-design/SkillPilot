"""threads 会话元信息读写（轻量，best-effort）。"""
from __future__ import annotations

import logging

from app.config import Config
from app.persistence import db

logger = logging.getLogger(__name__)


def upsert_thread(config: Config, thread_id: str, user_id: str) -> None:
    """记录/更新会话元信息。失败仅告警，不阻断主流程（降级方案）。"""
    if not config.database_url:
        return
    try:
        with db.connect(config) as conn:
            conn.execute(
                """
                INSERT INTO threads (thread_id, user_id, last_message_at)
                VALUES (%s, %s, now())
                ON CONFLICT (thread_id) DO UPDATE SET last_message_at = now()
                """,
                (thread_id, user_id),
            )
    except Exception:  # noqa: BLE001
        logger.warning("upsert thread metadata failed: thread=%s", thread_id, exc_info=True)
