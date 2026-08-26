"""阶段 7 长期记忆契约（memory/schemas）。

值对象与请求/响应模型：Namespace 命名空间、MemoryItem 语义/偏好/摘要事实、
MemorySearch、Episode 经历、PendingAction HITL 待确认动作。
"""
from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class Namespace(str, Enum):
    semantic = "semantic"
    procedural = "procedural"
    summary = "summary"


# Episodic 不落 memories，单列为一个事件类型集合，供事件校验复用
EVENT_TYPES = {
    "profile_updated",
    "gap_reported",
    "plan_generated",
    "plan_replanned",
    "practice_created",
    "evaluation_done",
    "conversation_summary",
}


class MemoryItem(BaseModel):
    """一条长期事实/偏好记忆（semantic/procedural/summary）。"""

    mem_id: str
    user_id: str
    namespace: str
    key: str
    text: str = ""
    payload: dict[str, Any] = Field(default_factory=dict)
    importance: float = 0.0
    created_at: Any = None
    updated_at: Any = None


class MemoryRememberRequest(BaseModel):
    user_id: str
    namespace: str = "semantic"
    key: str = Field(min_length=1, max_length=96)
    text: str = ""
    payload: dict[str, Any] = Field(default_factory=dict)
    importance: float = 0.0

    def ensure_namespace(self) -> str:
        if self.namespace not in (n.value for n in Namespace):
            raise ValueError(f"非法命名空间：{self.namespace}")
        return self.namespace


class MemorySearchRequest(BaseModel):
    user_id: str
    namespace: str | None = None
    query: str = ""
    top_k: int = 0

    def effective_top_k(self, default_top_k: int) -> int:
        return self.top_k if self.top_k > 0 else default_top_k


class MemorySearchResult(BaseModel):
    mem_id: str
    key: str
    text: str
    namespace: str
    payload: dict[str, Any] = Field(default_factory=dict)
    score: float = 0.0


class EpisodeRequest(BaseModel):
    """Episodic 记忆写入请求（成长轨迹，append-only）。"""

    user_id: str
    event_type: str
    ref_ids: dict[str, Any] = Field(default_factory=dict)
    summary: str = ""
    payload: dict[str, Any] = Field(default_factory=dict)


class Episode(BaseModel):
    event_id: str
    user_id: str
    event_type: str
    ref_ids: dict[str, Any] = Field(default_factory=dict)
    summary: str = ""
    payload: dict[str, Any] = Field(default_factory=dict)
    created_at: Any = None


class SummarizeRequest(BaseModel):
    user_id: str
    thread_id: str
    messages: list[dict[str, Any]] = Field(default_factory=list)


class PendingActionRequest(BaseModel):
    """HITL：创建一条待人工确认动作。"""

    user_id: str
    action_type: str
    payload: dict[str, Any] = Field(default_factory=dict)
    summary: str = ""


class PendingDecisionRequest(BaseModel):
    user_id: str
    decision: str  # approve | reject