"""实践任务编排（阶段 6，practice/planner）：LearningTask → PracticePlan。

deliverables / rubric 主体由规则按 level_target 生成（可重复）；guide 文案可选
LLM 润色，失败走模板兜底。不感知 HTTP。
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime

from app.config import Config
from app.gap import graph_store
from app.practice import explain, store
from app.practice.schemas import (
    PracticeCreateRequest,
    PracticeDeliverable,
    PracticePlan,
    RubricCriterion,
)
from app.todo import todo_store

logger = logging.getLogger(__name__)

# 交付物与评分准则（key 供评估端识别）
_DELIVERABLES = [
    ("code_repo", "可运行的 demo 代码库"),
    ("readme", "README：说明流程、依赖与运行方式"),
    ("tests", "含 1+ 个可运行的测试"),
]


def generate(config: Config, request: PracticeCreateRequest) -> PracticePlan:
    """由 LearningTask 生成实践计划并落库。"""
    resolved = todo_store.resolve_task(config, request.task_id)
    if resolved is None:
        raise ValueError("学习任务不存在或不属于任何计划")
    plan_id, task = resolved

    skill_id = task.skill_id or request.skill_id.strip()
    names = graph_store.load_skill_names(config)  # {id: name}
    skill_name = names.get(skill_id) or skill_id

    level_target = request.level_target or config.practice_default_level_target
    deliverables = _build_deliverables(level_target)
    rubric = _build_rubric(level_target)
    guide = explain.build_guide(skill_name, task.acceptance_criteria, level_target)
    polished = explain.llm_polish_guide(guide, config)

    plan = PracticePlan(
        practice_id=_new_id(),
        user_id=request.user_id,
        plan_id=plan_id,
        task_id=task.task_id,
        skill_id=skill_id,
        level_target=level_target,
        format=request.format,
        created_at=datetime.now().astimezone(),
        is_llm_enhanced=polished is not None,
        deliverables=deliverables,
        rubric=rubric,
        guide=polished or guide,
    )
    return store.create_practice(config, plan)


def _build_deliverables(level_target: int) -> list[PracticeDeliverable]:
    items = [PracticeDeliverable(key=k, desc=d) for k, d in _DELIVERABLES]
    if level_target >= 4:
        items.append(PracticeDeliverable(key="notes", desc="实践笔记：记录难点与踩坑，并用自己的话讲清核心概念"))
    return items


def _build_rubric(level_target: int) -> list[RubricCriterion]:
    # 目标越高，越重视测试与代码质量
    if level_target >= 4:
        return [
            RubricCriterion(criterion="功能实现", weight=0.35),
            RubricCriterion(criterion="测试覆盖", weight=0.3),
            RubricCriterion(criterion="代码结构与可读性", weight=0.2),
            RubricCriterion(criterion="文档可运行性", weight=0.15),
        ]
    return [
        RubricCriterion(criterion="功能实现", weight=0.4),
        RubricCriterion(criterion="代码结构与可读性", weight=0.2),
        RubricCriterion(criterion="测试覆盖", weight=0.25),
        RubricCriterion(criterion="文档可运行性", weight=0.15),
    ]


def _new_id() -> str:
    return f"PRA_{uuid.uuid4().hex[:12]}"