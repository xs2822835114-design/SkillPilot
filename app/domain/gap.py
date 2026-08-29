"""缺口契约（方案第 12 节）：技能缺口。"""
from __future__ import annotations

from pydantic import BaseModel, Field


class SkillGap(BaseModel):
    """单条技能缺口（由 GapEngine 确定性计算产出）。

    字段对齐方案第 12.1 节 SkillGap。
    """

    skill_id: str
    skill_name: str = ""
    current_level: int | None = None
    target_level: int = Field(default=3, ge=0, le=5)
    gap: int = 0
    priority: float = Field(default=0.0, ge=0.0)
    reasons: list[str] = Field(default_factory=list)