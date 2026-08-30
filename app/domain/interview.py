"""技能访谈契约（方案第 9、10、11 节）。

核心转变：问题不再是「固定 0~5 熟练度模板」，而是：
    SkillProfile(技能画像) + InterviewStrategy(访谈策略) → InterviewQuestion(单题) → 自适应推进

- SkillType：技能分类（与 knowledge.learning_metadata 的 LearningMode 对齐，作为访谈/学习的统一分类）；
- InterviewQuestionType：单题类型（按策略逐类型生成，机制题/概念题/API 题/场景题…）；
- InterviewStrategy：某类技能「该问哪些类型、问几题、是否自适应」的策略；
- InterviewQuestion / InterviewOption：结构化题目（给前端勾选 + 自由填写，选项内嵌行为证据关键词，
  供 Skill Engine 的 estimate_level 确定性推导等级）；
- InterviewState：跨轮会话状态（已问能力点 / 剩余能力点 / evidence），供 Checkpointer 持久化。

本模块只定义纯数据结构，不依赖 agents / engines / LLM。
"""
from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class SkillType(str, Enum):
    FRAMEWORK = "framework"
    LIBRARY = "library"
    API = "api"
    MECHANISM = "mechanism"
    CONCEPT = "concept"
    PATTERN = "pattern"
    LANGUAGE = "language"
    ARCHITECTURE = "architecture"


class InterviewQuestionType(str, Enum):
    CONCEPT = "concept"
    EXPERIENCE = "experience"
    API = "api"
    IMPLEMENTATION = "implementation"
    SCENARIO = "scenario"
    OPEN = "open"


class InterviewStrategy(BaseModel):
    """某类技能对应的访谈策略：决定按什么顺序、覆盖哪些能力点。"""

    skill_type: SkillType
    question_types: list[InterviewQuestionType] = Field(default_factory=list)
    max_questions: int = Field(default=4, ge=1, le=8)
    adaptive: bool = True


class InterviewOption(BaseModel):
    """单选项：``text`` 内嵌行为证据关键词，供 estimate_level 推导等级。"""

    id: str
    text: str
    band: int = 0  # 0~5 潜在证据等级（供渲染配色，实际等级以 estimate_level 结果为准）


class InterviewQuestion(BaseModel):
    """一条访谈题目：能力点锚定 + 类型化提问 + 技术化选项 + 自由填写入口。"""

    question_id: str
    skill_id: str
    skill_name: str = ""
    question_type: InterviewQuestionType = InterviewQuestionType.EXPERIENCE
    capability: str = ""          # 这道题要验证的能力点（core concept / api / scenario）
    prompt: str = ""              # 给前端页头 + 兜底纯文本提示（need_input 驱动）
    question: str = ""            # 题目正文
    options: list[InterviewOption] = Field(default_factory=list)
    allow_multiple: bool = True
    allow_free_text: bool = True
    index: int = 1
    total: int = 1


class InterviewState(BaseModel):
    """跨轮访谈状态（对齐架构方案第 17 节），由 Checkpointer 持久化。"""

    skill_id: str = ""
    current_skill: str = ""
    skill_queue: list[str] = Field(default_factory=list)
    asked_questions: list[str] = Field(default_factory=list)
    current_capabilities: list[str] = Field(default_factory=list)   # 当前技能待问的能力点
    asked_capabilities: list[str] = Field(default_factory=list)
    evidence: list[str] = Field(default_factory=list)
    remaining_capabilities: list[str] = Field(default_factory=list)
    question_count: int = 0
    active: bool = False
    finished: bool = False