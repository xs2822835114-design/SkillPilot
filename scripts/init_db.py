"""初始化数据库：创建 database（若不存在）与 users/threads 表（幂等）。

仅应在应用启动/迁移阶段执行一次：
    .venv/bin/python -m scripts.init_db
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import psycopg

from app.config import get_config


def _db_name(database_url: str) -> str:
    _, rest = database_url.split("://", 1)
    return rest.rsplit("/", 1)[-1]


def _admin_dsn(database_url: str) -> str:
    """将连接串指向管理库（postgres），以便创建目标库。"""
    scheme, rest = database_url.split("://", 1)
    host_part = rest.rsplit("/", 1)[0]
    return f"{scheme}://{host_part}/postgres"


def create_tables(conn) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id          VARCHAR(64) PRIMARY KEY,
            name        VARCHAR(128),
            target_role VARCHAR(64),
            created_at  TIMESTAMPTZ DEFAULT now()
        );
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS threads (
            thread_id       VARCHAR(64) PRIMARY KEY,
            user_id         VARCHAR(64) NOT NULL,
            title           VARCHAR(255),
            created_at      TIMESTAMPTZ DEFAULT now(),
            last_message_at TIMESTAMPTZ DEFAULT now()
        );
        """
    )
    print("users / threads 表已就绪")


def run() -> None:
    cfg = get_config()
    if not cfg.database_url:
        raise SystemExit("DATABASE_URL 未配置，无法初始化数据库")

    target = cfg.database_url
    dbname = _db_name(target)

    # 1) 确保目标库存在
    with psycopg.connect(_admin_dsn(target), autocommit=True) as conn:
        exists = conn.execute(
            "SELECT 1 FROM pg_database WHERE datname = %s", (dbname,)
        ).fetchone()
        if not exists:
            conn.execute(f'CREATE DATABASE "{dbname}"')
            print(f"已创建数据库 {dbname}")

    # 2) 连接目标库建表
    with psycopg.connect(target, autocommit=True) as conn:
        create_tables(conn)

    print("数据库初始化完成")


if __name__ == "__main__":
    run()
