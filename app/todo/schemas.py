"""学习规划 / Todo 层 Pydantic 契约（阶段 5）。

LearningPlan 为阶段 5 核心产物，也是阶段 6 Practice 的输入。契约对齐计划书
第 5 节 Planner Agent（PlanRequest → LearningPlan）。
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator

from app.gap.schemas import SkillGapReport, TargetSkill

# 任务状态机：pending → doing → done（V1 仅允许前向流转）
TASK_PENDING = "pending"
TASK_DOING = "doing"
TASK_DONE = "done"
VALID_TASK_STATUS = {TASK_PENDING, TASK_DOING, TASK_DONE}
VALID_TRANSITIONS = {TASK_PENDING: {TASK_DOING}, TASK_DOING: {TASK_DONE}}

PLAN_IN_PROGRESS = "in_progress"
PLAN_FINISHED = "finished"


# ---------------- 输入 ----------------

class PlanRequest(BaseModel):
    """POST /api/v1/plan/generate 请求契约。

    计划来源二选一：
      A) gap_report：直接传入阶段 4 的 SkillGapReport（推荐）；
      B) target_roles/target_skills：复用阶段 4 缺口入参，后端自动重算缺口。
    """

    user_id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,64}$")
    gap_report: SkillGapReport | None = None
    target_roles: list[str] = Field(default_factory=list, max_length=10)
    target_skills: list[TargetSkill] = Field(default_factory=list, max_length=30)
    available_hours_per_week: int = Field(default=5, ge=1, le=168)
    deadline: date | None = None
    learning_style: str | None = Field(default=None, max_length=64)
    phases_cap: int | None = Field(default=None, ge=1, le=30)

    @field_validator("user_id")
    @classmethod
    def _strip_user(cls, v: str) -> str:
        return v.strip()

    @field_validator("learning_style")
    @classmethod
    def _strip_style(cls, v: str | None) -> str | None:
        return (v or "").strip() or None

    def ensure_source(self) -> None:
        if self.gap_report is None and not self.target_roles and not self.target_skills:
            raise ValueError("gap_report 与 target_roles/target_skills 至少提供一种")


class ReplanRequest(BaseModel):
    """POST /api/v1/plan/{plan_id}/replan 请求契约。

    只重建 pending/doing 任务（done 任务保留、不回退）；缺省 gap_report 时沿用
    计划生成时的缺口快照。
    """

    gap_report: SkillGapReport | None = None
    feedback: str | None = Field(default=None, max_length=512)
    weekly_hours: int | None = Field(default=None, ge=1, le=168)

    @field_validator("feedback")
    @classmethod
    def _strip_feedback(cls, v: str | None) -> str | None:
        return (v or "").strip() or None


class TaskTransitionRequest(BaseModel):
    """POST /api/v1/plan/{plan_id}/tasks/{task_id}/transition 请求契约。"""

    action: str = Field(pattern=r"^(start|complete)$")


# ---------------- 输出 ----------------

class LearningResource(BaseModel):
    """任务推荐资源（来自 RAG，best-effort；无匹配则空列表）。"""

    title: str
    url: str | None = None
    source: str | None = None
    chunk_id: str | None = None


class LearningTask(BaseModel):
    """单条学习任务。status 依据状态机流转。"""

    task_id: str
    skill_id: str = ""
    title: str = ""
    estimated_hours: float = 4.0
    status: str = TASK_PENDING
    acceptance_criteria: str = ""
    resources: list[LearningResource] = Field(default_factory=list)
    required: bool = False
    order: int = 0


class LearningPhase(BaseModel):
    """一个阶段：skill_ids 共享同一拓扑深度，可并行学习。"""

    phase_id: str
    title: str = ""
    order: int = 0
    skill_ids: list[str] = Field(default_factory=list)
    tasks: list[LearningTask] = Field(default_factory=list)


class PlanMetrics(BaseModel):
    total_hours: float = 0.0
    total_tasks: int = 0
    done_tasks: int = 0
    weeks_est: int | None = None


class LearningPlan(BaseModel):
    """阶段 5 核心产物：有序、可执行、可验收、可恢复、可局部重规划的学习路线。"""

    plan_id: str
    user_id: str
    goal: str = ""
    source_role: str = ""
    created_at: datetime = Field(default_factory=lambda: datetime.now().astimezone())
    status: str = PLAN_IN_PROGRESS
    is_llm_enhanced: bool = False
    metrics: PlanMetrics = Field(default_factory=PlanMetrics)
    phases: list[LearningPhase] = Field(default_factory=list)


def as_dict(model: BaseModel) -> dict[str, Any]:
    return model.model_dump()