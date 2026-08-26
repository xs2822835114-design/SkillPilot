"""阶段 7 HITL 中间件（memory/middleware/hitl）：关键/破坏性操作暂停 → 人工确认。

park 创建待确认动作（pending_actions）；confirm 决策落库，未决/已决防重复；可列出待办。
守卫型操作接入方需在确认后再真正执行业务副作用（本中间件只记决策，不代行业务）。
"""
from __future__ import annotations

import logging
import uuid

from app.config import Config
from app.memory import store
from app.memory.schemas import PendingActionRequest

logger = logging.getLogger(__name__)


def _new_id() -> str:
    return f"PA_{uuid.uuid4().hex[:12]}"


def enabled(config: Config) -> bool:
    return getattr(config, "memory_hitl_enabled", True)


def expires(config: Config) -> int:
    return getattr(config, "memory_hitl_expires_seconds", 86400)


def park(config: Config, req: PendingActionRequest) -> str:
    """创建一条待人工确认动作；返回 pa_id。"""
    pa_id = _new_id()
    return store.create_pending(config, req, pa_id)


def list_pending(config: Config, user_id: str, status: str | None = None, limit: int = 50) -> list[dict]:
    return store.list_pending(config, user_id, status, limit)


def confirm(config: Config, pa_id: str, decision: str) -> str:
    """对动作做决策。value error 表示非法/已决/不存在，由调用方映射 422。"""
    return store.decide_pending(config, pa_id, decision, expires(config))