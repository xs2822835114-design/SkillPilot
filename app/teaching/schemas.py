"""AI 教学（Teaching）领域 Pydantic 契约。

职责边界（对齐「学习计划 → 学习任务 → AI 教学」三级结构）：
- LearningTask 已经是我们的小目标（学习目标），TeachingSession 只负责「怎么教」：
  概念讲解、示例代码、练习、验收，以及多轮互动（讲解 → 提问 → 判断 → 继续/重讲）。
- 不在此处再造一套「学习目标」结构；TeachingRequest 直接承载 LearningTask 的字段作为输入。
"""
from __future__ import annotations

import uuid

from pydantic import BaseModel, Field, field_validator

from app.domain.execution import ExecutionStep

# 教学对象 / 多轮互动角色
ROLE_AI = "ai"
ROLE_USER = "user"


def _new_session_id() -> str:
    return f"TEACH_{uuid.uuid4().hex[:12]}"


# ---------------- 输入 ----------------

class TeachingRequest(BaseModel):
    """TeachingAgent 的完整输入：直接复用 LearningTask 的字段与计划上下文。"""

    plan_id: str = ""
    task_id: str = ""
    user_id: str = ""

    goal: str = ""                       # 计划大目标（Plan.goal）
    skill_id: str = ""
    skill_name: str = ""

    task_title: str = ""
    learning_objective: str = ""         # <- 学习目标（取 task.title / acceptance_criteria）
    acceptance_criteria: str = ""

    execution_steps: list[ExecutionStep] = Field(default_factory=list)
    steps: list[str] = Field(default_factory=list)

    user_context: str | None = None


class TeachingStartRequest(BaseModel):
    """POST teach 请求契约。mode 当前仅支持 start（保留扩展位）。"""

    mode: str = Field(default="start", pattern=r"^start$")


class TeachingMessageRequest(BaseModel):
    """POST /teaching/<session_id>/message 请求契约（多轮互动）。"""

    message: str = Field(min_length=1, max_length=2000)

    @field_validator("message")
    @classmethod
    def _strip(cls, v: str) -> str:
        return v.strip()


# ---------------- 输出 ----------------

class TeachingConcept(BaseModel):
    title: str
    explanation: str


class TeachingExample(BaseModel):
    title: str
    explanation: str = ""
    code: str | None = None


class TeachingExercise(BaseModel):
    title: str
    instruction: str
    expected_result: str = ""
    hint: str = ""


class TeachingContent(BaseModel):
    concepts: list[TeachingConcept] = Field(default_factory=list)
    examples: list[TeachingExample] = Field(default_factory=list)
    exercises: list[TeachingExercise] = Field(default_factory=list)


class TeachingTurn(BaseModel):
    """一轮对话。ai 轮可附带结构化 content（如出题/验收）；user 轮为提问/回复。"""

    role: str
    message: str = ""
    mode: str = "explain"          # explain | question | exercise | verify
    content: TeachingContent | None = None


class TeachingSession(BaseModel):
    """一次「开始学习」产生的完整教学会话，支持多轮继续。"""

    session_id: str = Field(default_factory=_new_session_id)
    plan_id: str = ""
    task_id: str = ""
    user_id: str = ""

    title: str = ""
    learning_objective: str = ""
    acceptance_criteria: str = ""

    opening: str = ""
    content: TeachingContent = Field(default_factory=TeachingContent)

    status: str = "active"        # new | active | paused | completed（生命周期；关闭≠结束）
    current_step: int = 0         # 当前教学步骤索引（供恢复时继续）

    turns: list[TeachingTurn] = Field(default_factory=list)

    def append(self, turn: TeachingTurn) -> None:
        self.turns.append(turn)