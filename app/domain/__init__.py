"""领域层：全系统共享的 Pydantic 数据契约。

这是设计方案的底层核心——「Agent 负责理解与决策，数据结构负责描述事实，
Skill Graph 负责推理」，Agent 之间、Agent 与 Engine 之间通过本层契约传递数据。

本层不依赖 agents / engines / knowledge 等上层模块，只提供纯数据结构。
"""
from __future__ import annotations

from app.domain.intent import IntentResult, IntentType
from app.domain.skill import SkillRequirement, UserSkill
from app.domain.role import Role
from app.domain.requirement import JobRequirement, TechRequirement
from app.domain.profile import TargetProfile, UserSkillProfile

__all__ = [
    "IntentResult",
    "IntentType",
    "SkillRequirement",
    "UserSkill",
    "Role",
    "TechRequirement",
    "JobRequirement",
    "TargetProfile",
    "UserSkillProfile",
]