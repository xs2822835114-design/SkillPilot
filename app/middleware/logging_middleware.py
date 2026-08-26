"""请求日志中间件：每个请求输出一行结构化日志（含 trace 串联字段）。"""
from __future__ import annotations

import logging
import time

from flask import g, request

from app.middleware.trace import get_trace_id

logger = logging.getLogger("skillmap.access")


def setup_request_logging(app) -> None:
    @app.before_request
    def _start() -> None:
        g._req_start = time.perf_counter()

    @app.after_request
    def _log(resp):
        elapsed_ms = (time.perf_counter() - getattr(g, "_req_start", time.perf_counter())) * 1000
        body = request.get_json(silent=True) or {}
        logger.info(
            "request method=%s path=%s status=%s latency=%.1fms "
            "trace=%s user=%s thread=%s",
            request.method,
            request.path,
            resp.status_code,
            elapsed_ms,
            get_trace_id(),
            request.headers.get("X-User-ID", "-"),
            body.get("thread_id", "-"),
        )
        return resp
