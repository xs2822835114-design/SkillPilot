"""TC4 跨重启恢复 —— 基于真实 PostgreSQL（PostgresSaver）。

本机若无可用 PostgreSQL 则自动跳过（pytest.skip），其余测试不受影响。
"""
from __future__ import annotations

import os
import uuid

import pytest

TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL", "postgresql://localhost:5432/skillmap_test")


def _ensure_database() -> None:
    import psycopg

    scheme, rest = TEST_DATABASE_URL.split("://", 1)
    host_part = rest.rsplit("/", 1)[0]
    dbname = rest.rsplit("/", 1)[-1]
    admin_dsn = f"{scheme}://{host_part}/postgres"

    with psycopg.connect(admin_dsn, autocommit=True) as conn:
        exists = conn.execute(
            "SELECT 1 FROM pg_database WHERE datname = %s", (dbname,)
        ).fetchone()
        if not exists:
            conn.execute(f'CREATE DATABASE "{dbname}"')

    with psycopg.connect(TEST_DATABASE_URL, autocommit=True) as conn:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS users ("
            "id VARCHAR(64) PRIMARY KEY, name VARCHAR(128), target_role VARCHAR(64), "
            "created_at TIMESTAMPTZ DEFAULT now());"
        )
        conn.execute(
            "CREATE TABLE IF NOT EXISTS threads ("
            "thread_id VARCHAR(64) PRIMARY KEY, user_id VARCHAR(64) NOT NULL, "
            "title VARCHAR(255), created_at TIMESTAMPTZ DEFAULT now(), "
            "last_message_at TIMESTAMPTZ DEFAULT now());"
        )


@pytest.fixture(scope="module")
def pg_ready():
    try:
        _ensure_database()
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"PostgreSQL 不可用，跳过跨重启恢复测试: {exc}")
    return TEST_DATABASE_URL


def _make_app(database_url: str):
    from app import create_app
    from app.config import Config

    cfg = Config(
        env="test",
        database_url=database_url,
        llm_api_key="",  # 关闭 LLM，走规则兜底，保证确定性
        checkpointer_backend="postgres",
    )
    flask_app = create_app(cfg)
    flask_app.config["TESTING"] = True
    return flask_app


def test_tc4_restart_recovers_context(pg_ready):
    # 每次运行使用唯一 thread_id，避免跨运行 checkpoint 残留影响轮数断言
    thread_id = f"T_T4_{uuid.uuid4().hex[:8]}"

    # 第一次运行（进程 A）
    app1 = _make_app(pg_ready)
    r1 = app1.test_client().post(
        "/api/v1/chat",
        json={"user_id": "U10001", "thread_id": thread_id, "message": "我想转向 AI 应用开发"},
    )
    assert r1.status_code == 200

    # 模拟服务重启（进程 B）：新建应用实例，同库、同 thread
    app2 = _make_app(pg_ready)
    r2 = app2.test_client().post(
        "/api/v1/chat",
        json={"user_id": "U10001", "thread_id": thread_id, "message": "我还需要什么准备？"},
    )
    assert r2.status_code == 200
    reply = r2.get_json()["data"]["reply"]
    assert "继续这个话题" in reply          # 服务重启后仍恢复历史
    assert "想转向 AI 应用开发" in reply
