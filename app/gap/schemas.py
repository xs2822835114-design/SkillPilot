"""Skill Graph / Gap 层 Pydantic 契约（阶段 4）。

SkillGapReport 为阶段 4 核心产物，也是阶段 5 LearningPlan 的输入。
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator


# ---------------- 输入 ----------------


class TargetSkill(BaseModel):
    """target_skills 中单项目标能力：形如 {skill, level, weight}。"""

    skill: str = Field(min_length=1, max_length=128)
    level: int = Field(default=4, ge=0, le=5)
    weight: float = Field(default=1.0, ge=0.0, le=1.0)


class GapAnalysisRequest(BaseModel):
    """POST /api/v1/gap/request 请求契约。

    约束：target_roles 与 target_skills 至少提供一个；同时提供时以 target_roles
    为主，target_skills 视为额外追加要求。
    """

    user_id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,64}$")
    target_roles: list[str] = Field(default_factory=list, max_length=10)
    target_skills: list[TargetSkill] = Field(default_factory=list, max_length=30)
    profile_version: int | None = None
    top_gaps: int | None = Field(default=None, ge=1, le=200)

    @field_validator("user_id")
    @classmethod
    def _strip_user(cls, v: str) -> str:
        return v.strip()

    def ensure_target(self) -> None:
        if not self.target_roles and not self.target_skills:
            raise ValueError("target_roles 与 target_skills 至少提供一个")


# ---------------- 输出 ----------------


class PrereqItem(BaseModel):
    """缺口技能的前置（requires 传递展开）。own_gap_id 指向 gaps 中的自身条。"""

    skill_id: str
    name: str = ""
    status: str = "gap"          # gap | covered | required
    own_gap_id: str | None = None


class GapItem(BaseModel):
    """单条技能缺口。score/priority/reason/prerequisites/recommended_sequence 均规则计算。"""

    skill_id: str
    name: str = ""
    required_level: int = 0
    current_level: int = 0
    required_weight: float = 1.0
    score: float = 0.0
    priority: str = "P3"
    reason: str = ""
    prerequisites: list[PrereqItem] = Field(default_factory=list)
    recommended_sequence: list[str] = Field(default_factory=list)


class GapCoverage(BaseModel):
    required_total: int = 0
    covered_skills: list[str] = Field(default_factory=list)
    gap_skills: list[str] = Field(default_factory=list)
    gap_total: int = 0
    coverage_rate: float = 0.0


class SkillGapReport(BaseModel):
    """阶段 4 核心产物：画像 + 目标岗位 → 结构化、带优先级、可解释、可重复的缺口报告。"""

    user_id: str
    target_role_id: str
    target_role: str = ""
    role_category: str = ""
    profile_version_used: int = 0
    generated_at: datetime = Field(default_factory=lambda: datetime.now().astimezone())
    is_llm_enhanced: bool = False
    coverage: GapCoverage = Field(default_factory=GapCoverage)
    gaps: list[GapItem] = Field(default_factory=list)
    recommended_sequence: list[str] = Field(default_factory=list)
    suggestions: str = ""


class GapResponse(BaseModel):
    """gap/request 响应 data：target_roles 可多个，各产出一份 report。"""

    reports: list[SkillGapReport] = Field(default_factory=list)


def as_dict(model: BaseModel) -> dict[str, Any]:
    return model.model_dump()