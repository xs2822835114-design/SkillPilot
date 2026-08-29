"""意图契约（方案第 4 节）：顶层意图分类与识别结果。"""
from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class IntentType(str, Enum):
    """顶层三层意图：普通对话 / 技术学习 / 岗位求职。"""

    CHAT = "chat"
    TECH_LEARNING = "tech_learning"
    JOB_SEARCH = "job_search"


class IntentResult(BaseModel):
    """IntentRouter 识别结果。"""

    intent: IntentType = IntentType.CHAT
    confidence: float = Field(default=0.6, ge=0.0, le=1.0)
    reason: str | None = None