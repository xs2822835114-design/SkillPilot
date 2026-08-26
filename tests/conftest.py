"""pytest 夹具：创建隔离的应用实例（默认内存 checkpointer，不依赖真实 PostgreSQL）。"""
from __future__ import annotations

import pytest


@pytest.fixture()
def app():
    from app import create_app
    from app.config import Config

    cfg = Config(
        env="test",
        database_url="",
        llm_api_key="",          # 关闭 LLM，走规则兜底，保证确定性
        checkpointer_backend="memory",
    )
    flask_app = create_app(cfg)
    flask_app.config["TESTING"] = True
    return flask_app


@pytest.fixture()
def client(app):
    return app.test_client()
