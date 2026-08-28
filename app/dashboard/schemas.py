"""Dashboard 聚合 DTO（阶段 8，只读快照）。"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class SkillSummary(BaseModel):
    skill_id: str
    name: str = ""
    theory_score: int = 0
    practice_score: int = 0
    level: int = 0


class ProfileSummary(BaseModel):
    skill_count: int = 0
    skills: list[SkillSummary] = Field(default_factory=list)


class PlanSummary(BaseModel):
    plan_id: str
    goal: str = ""
    status: str = ""
    total_tasks: int = 0
    done_tasks: int = 0
    progress: float = 0.0


class EvalSummary(BaseModel):
    evaluation_id: str
    skill_id: str = ""
    overall_score: int = 0
    replanned: bool = False
    created_at: Any = None


class GrowthEvent(BaseModel):
    id: str
    event_type: str = ""
    summary: str = ""
    created_at: Any = None


class MemoryFact(BaseModel):
    key: str
    text: str = ""
    namespace: str = ""


class DashboardDTO(BaseModel):
    """概览首页 + 成长报告（Growth Report）数据，运行时聚合、不落库。"""

    user_id: str
    profile: ProfileSummary = Field(default_factory=ProfileSummary)
    latest_plan: PlanSummary | None = None
    latest_evaluation: EvalSummary | None = None
    growth: list[GrowthEvent] = Field(default_factory=list)
    facts: list[MemoryFact] = Field(default_factory=list)