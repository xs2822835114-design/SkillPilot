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
    user_goal: str | None        # 用户原始目标名（目标画像 goal_name / 目标岗位/技能）
    target_profile: dict | None  # 目标技能画像（TargetProfile 契约，供访谈/缺口复用）
    user_profile: dict | None    # 用户技能画像（UserSkillProfile 契约，访谈产出）
    skill_gaps: list             # 技能缺口（SkillGap 契约列表，GapEngine 产出）
    target_role: str | None
    skill_profile: dict
    skill_gap: dict
    learning_plan: dict
    practice_plan: dict
    evaluation_report: dict
    interview_state: dict          # 技能访谈会话状态（跨轮恢复，对齐架构方案第 17 节）
    retrieved_evidence: list
    memory_context: dict
    # 阶段 9：多 Agent 路由
    intent_params: dict          # 意图 → 结构化入参（目标岗位/技能/代码块等）
    summary: str                 # 业务节点产出的自然语言摘要（reply_node 拼接）
    artifacts: dict              # 透传给前端的精简业务结果（无业务时为 {}）
    # 运行时
    steps: list[str]         # 本轮已执行的节点/Agent 轨迹（intent_recognize → 业务节点 → reply）
    current_agent: str
    workflow_status: str
    error: dict | None
