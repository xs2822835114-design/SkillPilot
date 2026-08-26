"""请求/响应 Pydantic 契约（对齐计划书第 5、6 节）。"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, field_validator

from app.contracts import INTENT_HINTS


class Attachment(BaseModel):
    type: str = "file"
    file_id: str | None = None
    url: str | None = None
    mime_type: str | None = None


class UserRequest(BaseModel):
    """POST /api/v1/chat 请求体契约。"""

    user_id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,64}$")
    thread_id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,64}$")
    intent_hint: INTENT_HINTS | None = None
    message: str = Field(min_length=1, max_length=8000)
    attachments: list[Attachment] = Field(default_factory=list, max_length=5)

    @field_validator("message")
    @classmethod
    def _strip_message(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("message 不能为空")
        return v


class ChatResult(BaseModel):
    """POST /api/v1/chat 响应 data 契约。"""

    route: str = "chat"
    steps: list[str] = Field(default_factory=list)
    reason: str = ""
    reply: str = ""
    workflow_status: str = "done"
    artifacts: dict[str, Any] = Field(default_factory=dict)
    evidence: list[dict[str, Any]] = Field(default_factory=list)


def first_validation_error(exc: Exception) -> str:
    """从 Pydantic ValidationError 提取第一条错误信息。"""
    errors = getattr(exc, "errors", lambda: [])()
    if errors:
        first = errors[0]
        loc = ".".join(str(x) for x in first.get("loc", []))
        return f"{loc}: {first.get('msg', '参数错误')}"
    return "参数错误"
