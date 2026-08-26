"""SkillMap Flask 应用工厂。"""
from __future__ import annotations

import logging

from flask import Flask

from app.api.errors import register_error_handlers
from app.api.routes.chat import chat_bp
from app.api.routes.gap import gap_bp
from app.api.routes.health import health_bp
from app.api.routes.plan import plan_bp
from app.api.routes.profile import profile_bp
from app.api.routes.evaluation import eval_bp, practice_bp
from app.api.routes.rag import rag_bp
from app.api.routes.memory import memory_bp
from app.api.routes.dashboard import dashboard_bp
from app.api.routes.graph import graph_bp
from app.config import Config
from app.middleware.logging_middleware import setup_request_logging
from app.middleware.trace import init_trace


def create_app(config: Config | None = None) -> Flask:
    cfg = config or Config()
    app = Flask(__name__)

    # 配置与应用级组件挂在 extensions 上，路由经 current_app 取用，便于测试隔离
    app.extensions["skillmap"] = {"config": cfg, "graph": None}

    _setup_logging(cfg)

    @app.before_request
    def _before_request() -> None:
        init_trace()

    register_error_handlers(app)
    setup_request_logging(app)

    app.register_blueprint(health_bp)
    app.register_blueprint(chat_bp)
    app.register_blueprint(rag_bp)
    app.register_blueprint(profile_bp)
    app.register_blueprint(gap_bp)
    app.register_blueprint(plan_bp)
    app.register_blueprint(practice_bp)
    app.register_blueprint(eval_bp)
    app.register_blueprint(memory_bp)
    app.register_blueprint(graph_bp)
    app.register_blueprint(dashboard_bp)

    return app


def _setup_logging(cfg: Config) -> None:
    logging.basicConfig(
        level=getattr(logging, cfg.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )
