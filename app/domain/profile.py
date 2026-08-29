"""画像契约（方案第 8、10 节）：目标画像与用户画像。"""
from __future__ import annotations

from datetime import datetime, timezone

from pydantic import BaseModel, Field

from app.domain.skill import SkillRequirement, UserSkill


class TargetProfile(BaseModel):
    """目标技能画像：技术目标与岗位目标统一转换后的技能要求集合。

    字段对齐方案第 8 节 TargetProfile。
    """

    goal_type: str = "tech_learning"  # tech_learning | job_search
    goal_name: str = ""
    skills: list[SkillRequirement] = Field(default_factory=list)


class UserSkillProfile(BaseModel):
    """用户技能画像：由访谈证据驱动的技能集合。

    字段对齐方案第 10 节 UserSkillProfile。
    """

    user_id: str
    skills: list[UserSkill] = Field(default_factory=list)
    last_updated: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))