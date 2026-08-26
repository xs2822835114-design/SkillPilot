"""SkillMap Flask 应用工厂。"""
from __future__ import annotations

import logging

from flask import Flask, jsonify, request

from app.api.errors import register_error_handlers
from app.api.routes.chat import chat_bp
from app.api.routes.graph import graph_bp
from app.api.routes.health import health_bp
from app.api.routes.plan import plan_bp
from app.config import Config
from app.middleware.logging_middleware import setup_request_logging
from app.middleware.trace import init_trace


def _apply_cors(app: Flask) -> None:
    """轻量 CORS：允许跨源(SkillMap 前端 / API 直连)访问，支持 SSE 流式直连后端。"""

    @app.before_request
    def _cors_preflight() -> None:
        if request.method == "OPTIONS":
            resp = jsonify({})
            resp.headers.add("Access-Control-Allow-Origin", "*")
            resp.headers.add("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            resp.headers.add("Access-Control-Allow-Headers", "Content-Type, Authorization")
            return resp

    @app.after_request
    def _cors_headers(response):  # noqa: ANN001
        response.headers.add("Access-Control-Allow-Origin", "*")
        return response


def create_app(config: Config | None = None) -> Flask:
    cfg = config or Config()
    app = Flask(__name__)

    # 配置与应用级组件挂在 extensions 上，路由经 current_app 取用，便于测试隔离
    app.extensions["skillmap"] = {"config": cfg, "graph": None}

    _setup_logging(cfg)
    _apply_cors(app)

    @app.before_request
    def _before_request() -> None:
        init_trace()

    register_error_handlers(app)
    setup_request_logging(app)

    app.register_blueprint(health_bp)
    app.register_blueprint(chat_bp)
    app.register_blueprint(plan_bp)
    app.register_blueprint(graph_bp)

    return app


def _setup_logging(cfg: Config) -> None:
    logging.basicConfig(
        level=getattr(logging, cfg.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )
