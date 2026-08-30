"""教学会话内存存储（单进程 Demo 形态，跨请求按 session_id 恢复多轮互动）。

存放的是 TeachingSession 及其轮询历史；不落库，进程重启即失效。
若后续需要持久化，可仿照 todo_store 以 session_id 为键写到 DB，接口保持不变。
"""
from __future__ import annotations

import threading

from app.teaching.schemas import TeachingSession

_lock = threading.Lock()
_sessions: dict[str, TeachingSession] = {}


def put(session: TeachingSession) -> TeachingSession:
    with _lock:
        _sessions[session.session_id] = session
    return session


def get(session_id: str) -> TeachingSession | None:
    with _lock:
        return _sessions.get(session_id)