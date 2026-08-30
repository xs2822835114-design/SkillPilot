"""访谈策略（InterviewStrategy）：技能分类 → 该问哪些类型的能力点。

与 Goal：不同 skill_type 的访谈路径不同 —— 这是「问题不是模子刻出来」的关键：
    Checkpoint   → mechanism → 概念 / 经验 / 场景 / 开放
    LangGraph    → framework → 概念 / 经验 / 实现 / 场景
    LLM API      → api       → 概念 / API / 场景

策略本身是确定性的（不靠 LLM），真正问什么题由 Interview Agent 基于
SkillProfile（core_concepts / core_apis / practice_context）生成。
"""
from __future__ import annotations

from app.domain.interview import InterviewQuestionType, InterviewStrategy, SkillType
from app.knowledge.learning_metadata import SkillLearningProfile

# 每种技能类型 → 按优先级排列的问题类型序列
INTERVIEW_STRATEGIES: dict[SkillType, list[InterviewQuestionType]] = {
    SkillType.FRAMEWORK: [
        InterviewQuestionType.CONCEPT,
        InterviewQuestionType.EXPERIENCE,
        InterviewQuestionType.IMPLEMENTATION,
        InterviewQuestionType.SCENARIO,
    ],
    SkillType.LIBRARY: [
        InterviewQuestionType.CONCEPT,
        InterviewQuestionType.API,
        InterviewQuestionType.EXPERIENCE,
        InterviewQuestionType.SCENARIO,
    ],
    SkillType.API: [
        InterviewQuestionType.CONCEPT,
        InterviewQuestionType.API,
        InterviewQuestionType.SCENARIO,
    ],
    SkillType.MECHANISM: [
        InterviewQuestionType.CONCEPT,
        InterviewQuestionType.EXPERIENCE,
        InterviewQuestionType.SCENARIO,
        InterviewQuestionType.OPEN,
    ],
    SkillType.PATTERN: [
        InterviewQuestionType.CONCEPT,
        InterviewQuestionType.IMPLEMENTATION,
        InterviewQuestionType.SCENARIO,
        InterviewQuestionType.OPEN,
    ],
    SkillType.CONCEPT: [
        InterviewQuestionType.CONCEPT,
        InterviewQuestionType.SCENARIO,
        InterviewQuestionType.OPEN,
    ],
    SkillType.LANGUAGE: [
        InterviewQuestionType.CONCEPT,
        InterviewQuestionType.EXPERIENCE,
        InterviewQuestionType.SCENARIO,
    ],
    SkillType.ARCHITECTURE: [
        InterviewQuestionType.CONCEPT,
        InterviewQuestionType.EXPERIENCE,
        InterviewQuestionType.SCENARIO,
        InterviewQuestionType.OPEN,
    ],
}

_DEFAULT_STRATEGY = SkillType.MECHANISM


def build_strategy(profile: SkillLearningProfile, max_questions: int | None = None) -> InterviewStrategy:
    """由技能画像生成访谈策略：skill_type 决定问题类型序列。

    ``max_questions=None`` 时用类型序列长度；否则截断到该上限（≥1）。
    """
    stype = SkillType(profile.learning_mode.value) if _valid_mode(profile.learning_mode.value) else _DEFAULT_STRATEGY
    qtypes = INTERVIEW_STRATEGIES.get(stype, INTERVIEW_STRATEGIES.get(_DEFAULT_STRATEGY, []))
    cap = max_questions
    if cap is None or int(cap) <= 0:  # 0/None → 用完整题型序列
        cap = len(qtypes)
    cap = max(1, min(8, int(cap)))
    return InterviewStrategy(
        skill_type=stype,
        question_types=qtypes[:cap],
        max_questions=cap,
        adaptive=True,
    )


def _valid_mode(value: str) -> bool:
    try:
        SkillType(value)
        return True
    except ValueError:
        return False