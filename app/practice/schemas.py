"""实践任务层 Pydantic 契约（阶段 6）。

依赖：阶段 5 的 LearningTask（skill_id / acceptance_criteria / level）。
PracticePlan 为阶段 6 Evaluation 的评估输入来源。
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator

VALID_FORMATS = {"project"}


class PracticeCreateRequest(BaseModel):
    """POST /api/v1/practice/generate 请求契约（来源于某条 LearningTask）。"""

    user_id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,64}$")
    task_id: str = Field(min_length=3, max_length=127)
    skill_id: str = Field(max_length=64)
    level_target: int | None = Field(default=None, ge=1, le=5)
    format: str = Field(default="project")

    @field_validator("skill_id")
    @classmethod
    def _strip_skill(cls, v: str) -> str:
        return (v or "").strip()

    @field_validator("format")
    @classmethod
    def _check_format(cls, v: str) -> str:
        if v not in VALID_FORMATS:
            raise ValueError(f"format 暂不支持: {v}")
        return v


class PracticeDeliverable(BaseModel):
    key: str
    desc: str = ""


class RubricCriterion(BaseModel):
    criterion: str
    weight: float = 0.0


class PracticePlan(BaseModel):
    practice_id: str
    user_id: str
    plan_id: str = ""
    task_id: str = ""
    skill_id: str = ""
    level_target: int = 1
    format: str = "project"
    created_at: datetime = Field(default_factory=lambda: datetime.now().astimezone())
    is_llm_enhanced: bool = False
    deliverables: list[PracticeDeliverable] = Field(default_factory=list)
    rubric: list[RubricCriterion] = Field(default_factory=list)
    guide: str = ""


def as_dict(model: BaseModel) -> dict[str, Any]:
    return model.model_dump(mode="json")