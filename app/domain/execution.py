"""执行计划领域契约（TaskRefinementAgent 产物）。

设计原则（见方案「执行计划精炼 Agent」）：
- Planner 只回答「学什么 / 先学什么 / 学多久」；
- TaskRefinementAgent 只回答「怎么学 / 做什么 / 产出什么 / 如何验证」。
- 本层为纯数据结构，不依赖 agents / engines / knowledge 等上层模块，
  仅以 `resources`(dict 列表) 承载可选的资源引用，避免跨层强依赖。
"""
from __future__ import annotations

from pydantic import BaseModel, Field


class ExecutionStep(BaseModel):
    """单个原子化执行步骤。

    核心要求（原子化 + 可验证）：
    - 每个步骤只做一件事；
    - action/instructions 是「打开电脑具体做什么」，而非泛泛的阶段名；
    - deliverable 说明完成后留下什么可观察产物；
    - verification 说明怎么确认自己真的完成了。
    """

    step_id: str
    title: str
    action: str = ""
    instructions: list[str] = Field(default_factory=list)
    deliverable: str = ""
    verification: str = ""
    estimated_minutes: int = Field(default=30, ge=5, le=240)
    resources: list[dict] = Field(default_factory=list)


class TaskRefinementInput(BaseModel):
    """Refiner 的输入压缩：不必把整个 LearningPlan 扔给 LLM。"""

    task_id: str
    skill_id: str = ""
    skill_name: str = ""
    goal: str = ""
    gap: int = 1
    estimated_hours: float = 4.0
    acceptance_criteria: str = ""
    existing_steps: list[str] = Field(default_factory=list)


class RefinedTask(BaseModel):
    """Refiner 的结构化输出：把一条 LearningTask 精炼成可照做的执行任务。"""

    task_id: str
    title: str = ""
    learning_objective: str = ""
    acceptance_criteria: str = ""
    execution_steps: list[ExecutionStep] = Field(default_factory=list)
    total_estimated_minutes: int = 0
    is_refined: bool = True


__all__ = ["ExecutionStep", "TaskRefinementInput", "RefinedTask"]