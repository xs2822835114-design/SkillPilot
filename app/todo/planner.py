"""学习规划编排（阶段 5，planner）：SkillGapReport + 时间/偏好 → LearningPlan。

职责：解析计划来源（A 直传 report / B 复用缺口入参自算）、调用 scheduler 分桶、
explain 生成任务文案与资源、todo_store 落库；replan 负责局部重规划（保留 done）。
不感知 HTTP。
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime

from app.config import Config
from app.gap import gap_agent, graph_store
from app.gap.schemas import GapAnalysisRequest, SkillGapReport
from app.todo import explain, scheduler, todo_store
from app.todo.schemas import (
    TASK_DONE,
    LearningPlan,
    LearningPhase,
    LearningTask,
    PlanRequest,
    ReplanRequest,
)

logger = logging.getLogger(__name__)


def generate(config: Config, request: PlanRequest) -> LearningPlan:
    """生成一份 LearningPlan 并落库。plan_id 重新生成。"""
    report = request.gap_report or _compute_report(config, request)
    plan = _build_plan(
        config,
        report,
        plan_id=_new_plan_id(),
        user_id=request.user_id,
        weekly_hours=request.available_hours_per_week,
        phases_cap=request.phases_cap,
        goal_override=None,
        learning_style=request.learning_style,
        done_skills=frozenset(),
    )
    _refine(config, plan)
    todo_store.create_plan(
        config, plan,
        report=report.model_dump(mode="json"),
        skill_ids=list(report.recommended_sequence),
    )
    return plan


def replan(config: Config, plan_id: str, request: ReplanRequest) -> LearningPlan:
    """局部重规划：只重建 pending/doing 任务；done 任务保留、不回退。"""
    existing = todo_store.load_plan(config, plan_id)
    if existing is None:
        raise ValueError("学习计划不存在")

    if request.gap_report:
        report = request.gap_report
    else:
        stored = todo_store.load_plan_report(config, plan_id)
        if not stored:
            raise ValueError("学习计划缺少缺口快照，无法重规划")
        report = SkillGapReport(**stored)

    done_skills = {
        t.skill_id
        for phase in existing.phases
        for t in phase.tasks
        if t.status == TASK_DONE and t.skill_id
    }
    plan = _build_plan(
        config,
        report,
        plan_id=plan_id,
        user_id=existing.user_id,
        weekly_hours=request.weekly_hours or existing.metrics.weeks_est or 0,
        phases_cap=None,
        goal_override=existing.goal,
        learning_style=None,
        done_skills=frozenset(done_skills),
    )
    plan.created_at = existing.created_at
    _refine(config, plan)
    todo_store.create_plan(
        config, plan,
        report=report.model_dump(mode="json"),
        skill_ids=list(report.recommended_sequence),
    )
    return plan


def _refine(config: Config, plan: LearningPlan) -> None:
    """在 Planner 后精炼每条任务为执行级步骤（TaskRefinementAgent）。"""
    try:
        from app.agents.task_refinement import refine_learning_plan

        refine_learning_plan(config, plan)
    except Exception:  # noqa: BLE001 - 精炼为增强型能力，失败不阻断计划生成
        logger.warning("学习计划执行级精炼未完成，沿用粗粒度步骤", exc_info=True)


def _compute_report(config: Config, request: PlanRequest) -> SkillGapReport:
    """B 路：复用阶段 4 缺口计算，取第一份 report（多岗位时按序取首）。"""
    reports = gap_agent.analyze(
        config,
        GapAnalysisRequest(
            user_id=request.user_id,
            target_roles=request.target_roles,
            target_skills=request.target_skills,
        ),
    ).reports
    if not reports:
        raise ValueError("未计算出缺口，无法生成学习计划")
    return reports[0]


def _build_plan(
    config: Config,
    report: SkillGapReport,
    plan_id: str,
    user_id: str,
    weekly_hours: int,
    phases_cap: int | None,
    goal_override: str | None,
    learning_style: str | None,
    done_skills: frozenset[str],
) -> LearningPlan:
    edges = graph_store.load_requires_edges(config)
    names = graph_store.load_skill_names(config)
    deltas = scheduler.skill_deltas(report)
    groups = scheduler.split_phases(report, edges, phases_cap)

    phases: list[LearningPhase] = []
    all_tasks: list[LearningTask] = []
    counter = 0
    for gidx, group in enumerate(groups, start=1):
        phase_tasks: list[LearningTask] = []
        for order, skill in enumerate(group, start=1):
            counter += 1
            name = names.get(skill, skill)
            delta = deltas.get(skill, 1)
            done = skill in done_skills
            phase_tasks.append(
                LearningTask(
                    task_id=_new_task_id(plan_id, counter),
                    skill_id=skill,
                    title=explain.build_task_title(name, delta, "P1"),
                    estimated_hours=scheduler.estimate_hours(
                        delta, config.plan_min_task_hours, config.plan_max_task_hours,
                        config.plan_hours_per_level,
                    ),
                    status=TASK_DONE if done else "pending",
                    acceptance_criteria=explain.build_acceptance(name, delta),
                    steps=explain.build_steps(config, name, skill, delta),
                    resources=explain.resources_for_skill(config, skill, name),
                    required=not done,
                    order=order,
                )
            )
        phases.append(
            LearningPhase(
                phase_id=f"P{gidx}",
                title=explain.build_phase_title(group, names),
                order=gidx,
                skill_ids=list(group),
                tasks=phase_tasks,
            )
        )
        all_tasks.extend(phase_tasks)

    goal = goal_override or explain.build_goal(report.target_role)
    polished = explain.llm_polish_goal(goal, learning_style) if not goal_override else None
    return LearningPlan(
        plan_id=plan_id,
        user_id=user_id,
        goal=polished or goal,
        source_role=report.target_role_id,
        created_at=datetime.now().astimezone(),
        status="in_progress",
        is_llm_enhanced=polished is not None,
        metrics=_metrics(config, all_tasks, weekly_hours),
        phases=phases,
    )


def _metrics(config: Config, tasks: list[LearningTask], weekly_hours: int):
    from app.todo.schemas import PlanMetrics

    return PlanMetrics(**scheduler.compute_metrics(
        tasks,
        weekly_hours if weekly_hours and weekly_hours > 0 else config.plan_default_weekly_hours,
    ))


def _new_plan_id() -> str:
    return f"PLAN_{uuid.uuid4().hex[:12]}"


def _new_task_id(plan_id: str, counter: int) -> str:
    return f"{plan_id}-T{counter:02d}"