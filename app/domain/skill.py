"""技能契约（方案第 7、10、11 节）：统一技能需求与用户技能。"""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class SkillRequirement(BaseModel):
    """统一技能需求：无论技术目标还是岗位目标，最终都落到同一种技能要求。

    字段对齐方案第 7 节 SkillRequirement。
    """

    skill_id: str
    skill_name: str = ""
    required_level: int = Field(default=3, ge=0, le=5)
    weight: float = Field(default=1.0, ge=0.0, le=1.0)
    reason: str | None = None
    source: str | None = None


class UserSkill(BaseModel):
    """用户单条技能：由行为证据驱动，保留 level/confidence/evidence 三个核心字段。

    字段对齐方案第 10、11 节 UserSkill。
    """

    skill_id: str
    skill_name: str = ""
    level: int | None = None
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    evidence: list[str] = Field(default_factory=list)
    source: str = "conversation"
    last_updated: datetime | None = None