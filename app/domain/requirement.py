"""需求契约（方案第 5、6 节）：技术需求与岗位需求。"""
from __future__ import annotations

from pydantic import BaseModel, Field

from app.domain.skill import SkillRequirement


class TechRequirement(BaseModel):
    """技术学习目标的结构化需求（由 TechRequirementAgent 产出）。

    字段对齐方案第 5.1 节。
    """

    goal: str = Field(min_length=1)
    target_skills: list[str] = Field(default_factory=list)
    related_skills: list[str] = Field(default_factory=list)
    prerequisites: list[str] = Field(default_factory=list)
    context: str | None = None


class JobRequirement(BaseModel):
    """岗位求职目标的结构化需求（由 JobRequirementAgent 产出）。

    字段对齐方案第 6.1 节。
    """

    role_id: str = Field(min_length=1)
    role_name: str = ""
    target_level: str | None = None
    required_skills: list[SkillRequirement] = Field(default_factory=list)