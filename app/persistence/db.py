"""PostgreSQL 连接管理（engine/session 工厂）。"""
from __future__ import annotations

import logging
from contextlib import contextmanager
from typing import Iterator

import psycopg

from app.config import Config

logger = logging.getLogger(__name__)


@contextmanager
def connect(config: Config) -> Iterator[psycopg.Connection]:
    """打开一个 autocommit 的 PostgreSQL 连接（用后自动关闭）。"""
    if not config.database_url:
        raise RuntimeError("DATABASE_URL 未配置")
    conn = psycopg.connect(config.database_url, autocommit=True)
    try:
        yield conn
    finally:
        conn.close()


def ping(config: Config) -> bool:
    """探测数据库连通性（供 /health 使用）。"""
    if not config.database_url:
        return False
    try:
        with connect(config) as conn:
            conn.execute("SELECT 1")
        return True
    except Exception:  # noqa: BLE001
        logger.warning("DB ping failed", exc_info=True)
        return False
