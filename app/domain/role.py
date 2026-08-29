"""岗位契约：岗位能力定义快照（来自岗位能力知识库，方案第 6、19 节）。"""
from __future__ import annotations

from pydantic import BaseModel, Field

from app.domain.skill import SkillRequirement


class Role(BaseModel):
    """岗位能力定义，作为岗位知识库（role_competencies）的统一读取结构。"""

    role_id: str
    role_name: str = ""
    category: str = ""
    seniority: str = ""
    summary: str = ""
    required_skills: list[SkillRequirement] = Field(default_factory=list)