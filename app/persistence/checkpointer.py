"""Checkpointer 初始化（仅应用启动/迁移阶段执行一次）。"""
from __future__ import annotations

import logging
from typing import Any

from app.config import Config

logger = logging.getLogger(__name__)


def get_checkpointer(config: Config) -> Any:
    """按配置返回 checkpointer：postgres 优先，无 DB 时回退内存实现。

    backend = auto 时：配置了 DATABASE_URL 用 postgres，否则用 memory。
    """
    backend = config.checkpointer_backend
    if backend == "auto":
        backend = "postgres" if config.database_url else "memory"

    if backend == "postgres":
        return _build_postgres_checkpointer(config)
    return _build_memory_checkpointer()


def _build_postgres_checkpointer(config: Config) -> Any:
    from langgraph.checkpoint.postgres import PostgresSaver
    from psycopg import Connection

    conn = Connection.connect(config.database_url, autocommit=True)
    checkpointer = PostgresSaver(conn)
    # 建表/迁移仅在初始化阶段执行，不放在业务写入路径
    checkpointer.setup()
    logger.info("PostgresSaver checkpointer initialized")
    return checkpointer


def _build_memory_checkpointer() -> Any:
    from langgraph.checkpoint.memory import InMemorySaver

    logger.info("InMemorySaver checkpointer initialized (dev/test only)")
    return InMemorySaver()
