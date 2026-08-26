"""trace_id 生成与传递。"""
from __future__ import annotations

import uuid

from flask import g, request


def _new_trace_id() -> str:
    return f"trc_{uuid.uuid4().hex[:12]}"


def init_trace() -> None:
    """每个请求开始时调用：优先取 X-Trace-ID，否则自动生成。"""
    g.trace_id = request.headers.get("X-Trace-ID") or _new_trace_id()


def get_trace_id() -> str:
    return getattr(g, "trace_id", "")
