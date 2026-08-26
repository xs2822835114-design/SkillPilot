"""SkillMapState —— 编排层运行时状态（一次性定义完整，对齐计划书第 6 节）。"""
from __future__ import annotations

from typing import Any, TypedDict


class SkillMapState(TypedDict, total=False):
    # 对话上下文（历史 + 本轮，持久化到 Checkpointer）
    messages: list[dict[str, Any]]
    # 本次输入
    user_id: str
    thread_id: str
    message: str
    intent_hint: str | None
    intent: str
    # 业务状态快照（阶段 1 为空占位，阶段 3~6 填充）
    target_role: str | None
    skill_profile: dict
    skill_gap: dict
    learning_plan: dict
    practice_plan: dict
    evaluation_report: dict
    retrieved_evidence: list
    memory_context: dict
    # 运行时
    current_agent: str
    workflow_status: str
    error: dict | None
