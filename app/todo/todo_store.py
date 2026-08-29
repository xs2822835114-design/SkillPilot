"""学习计划/任务存储与状态流转（阶段 5，todo_store）（psycopg 直连）。

负责：建计划落库、按 plan_id 查询/恢复、任务状态机 pending→doing→done、计划
汇总状态。不含调度/顺序计算。对外异常统一抛 ValueError（业务语义错误，由调用方
映射为 HTTP）。
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from app.config import Config
from app.persistence import db as pgdb
from app.todo.schemas import (
    PLAN_FINISHED,
    PLAN_IN_PROGRESS,
    TASK_DOING,
    TASK_DONE,
    VALID_TRANSITIONS,
    LearningPlan,
    LearningPhase,
    LearningResource,
    LearningTask,
    PlanMetrics,
)

logger = logging.getLogger(__name__)


def create_plan(config: Config, plan: LearningPlan, report: dict, skill_ids: list[str]) -> LearningPlan:
    """把计算好的 LearningPlan 落库（重跑计划时先按 plan_id 清旧任务再写）。"""
    with pgdb.connect(config) as conn:
        _ensure_steps_column(conn)
        conn.execute(
            """
            DELETE FROM learning_tasks WHERE plan_id = %s
            """,
            (plan.plan_id,),
        )
        conn.execute(
            """
            INSERT INTO learning_plans
              (id, user_id, goal, source_role, status, skill_ids, report_json,
               metrics_json, is_llm_enhanced, created_at, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, now())
            ON CONFLICT (id) DO UPDATE SET
              goal=%s, source_role=%s, status=%s, skill_ids=%s, report_json=%s,
              metrics_json=%s, is_llm_enhanced=%s, updated_at=now()
            """,
            (
                plan.plan_id,
                plan.user_id,
                plan.goal,
                plan.source_role,
                plan.status,
                Jsonb(skill_ids),
                Jsonb(report),
                Jsonb(plan.metrics.model_dump()),
                plan.is_llm_enhanced,
                plan.created_at,
                plan.goal,
                plan.source_role,
                plan.status,
                Jsonb(skill_ids),
                Jsonb(report),
                Jsonb(plan.metrics.model_dump()),
                plan.is_llm_enhanced,
            ),
        )
        for phase in plan.phases:
            for task in phase.tasks:
                _insert_task(conn, plan.plan_id, phase, task)
    return plan


def _insert_task(conn, plan_id: str, phase: LearningPhase, task: LearningTask) -> None:
    started_at = _now() if task.status == TASK_DOING else None
    finished_at = _now() if task.status == TASK_DONE else None
    conn.execute(
        """
        INSERT INTO learning_tasks
          (id, plan_id, phase_id, phase_order, task_order, skill_id, title,
           estimated_hours, status, acceptance_criteria, resources_json, steps_json,
           required, started_at, finished_at, created_at, updated_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, now(), now())
        """,
        (
            task.task_id,
            plan_id,
            phase.phase_id,
            phase.order,
            task.order,
            task.skill_id,
            task.title,
            task.estimated_hours,
            task.status,
            task.acceptance_criteria,
            Jsonb([r.model_dump() for r in task.resources]),
            Jsonb(task.steps),
            task.required,
            started_at,
            finished_at,
        ),
    )


def _now() -> datetime:
    return datetime.now().astimezone()


def _ensure_steps_column(conn) -> None:
    """幂等补齐 learning_tasks.steps_json 列（历史库升级；新建库由 init_db 建表时已含）。"""
    conn.execute("ALTER TABLE learning_tasks ADD COLUMN IF NOT EXISTS steps_json JSONB")


def load_plan(config: Config, plan_id: str) -> LearningPlan | None:
    with pgdb.connect(config) as conn:
        _ensure_steps_column(conn)
        conn.row_factory = dict_row
        row = conn.execute(
            "SELECT * FROM learning_plans WHERE id = %s", (plan_id,)
        ).fetchone()
        if not row:
            return None
        rows = conn.execute(
            """
            SELECT * FROM learning_tasks
            WHERE plan_id = %s
            ORDER BY phase_order, task_order
            """,
            (plan_id,),
        ).fetchall()

    phases: dict[int, LearningPhase] = {}
    all_tasks: list[LearningTask] = []
    for r in rows:
        task = LearningTask(
            task_id=r["id"],
            skill_id=r["skill_id"] or "",
            title=r["title"] or "",
            estimated_hours=float(r["estimated_hours"] or 0),
            status=r["status"],
            acceptance_criteria=r["acceptance_criteria"] or "",
            steps=list(r["steps_json"] or []),
            resources=[LearningResource(**x) for x in (r["resources_json"] or [])],
            required=bool(r["required"]),
            order=int(r["task_order"]),
        )
        all_tasks.append(task)
        phase = phases.setdefault(
            r["phase_order"],
            LearningPhase(phase_id=r["phase_id"], title="", order=r["phase_order"]),
        )
        phase.tasks.append(task)
    for phase in phases.values():
        phase.skill_ids = list(dict.fromkeys(t.skill_id for t in phase.tasks if t.skill_id))

    plan = LearningPlan(
        plan_id=row["id"],
        user_id=row["user_id"],
        goal=row["goal"] or "",
        source_role=row["source_role"] or "",
        created_at=row["created_at"],
        status=row["status"],
        is_llm_enhanced=bool(row["is_llm_enhanced"]),
        metrics=PlanMetrics(**(row["metrics_json"] or {})),
        phases=[phases[k] for k in sorted(phases)],
    )
    # 动态重算 metrics 与状态（状态流转会改变 done_tasks）
    from app.todo import scheduler

    plan.metrics = PlanMetrics(**scheduler.compute_metrics(all_tasks, plan.metrics.weeks_est))
    _refresh_status(config, plan)
    _persist_status(config, plan)
    return plan


def _persist_status(config: Config, plan: LearningPlan) -> None:
    """把最新状态与 metrics 回写（保持库内快照与内存一致）。"""
    if not plan.metrics.total_tasks:
        return
    with pgdb.connect(config) as conn:
        conn.execute(
            """
            UPDATE learning_plans
            SET status=%s, metrics_json=%s, updated_at=now()
            WHERE id=%s
            """,
            (plan.status, Jsonb(plan.metrics.model_dump()), plan.plan_id),
        )


def resolve_task(config: Config, task_id: str) -> tuple[str, LearningTask] | None:
    """按任务全局唯一 id 定位其所属计划与任务（id 形如 `<plan_id>-T01`）。"""
    dash = task_id.rfind("-T")
    if dash < 0:
        return None
    plan_id = task_id[:dash]
    plan = load_plan(config, plan_id)
    if plan is None:
        return None
    for phase in plan.phases:
        for t in phase.tasks:
            if t.task_id == task_id:
                return plan_id, t
    return None


def load_plan_report(config: Config, plan_id: str) -> dict | None:
    """读取计划生成时所依据的缺口快照（供 replan 复用）。"""
    with pgdb.connect(config) as conn:
        row = conn.execute(
            "SELECT report_json FROM learning_plans WHERE id = %s", (plan_id,)
        ).fetchone()
    return dict(row[0]) if row and row[0] else None


def delete_user_plans(config: Config, user_id: str) -> int:
    """级联删除某用户的全部学习计划（任务与计划一并清空），返回删除的计划数。"""
    with pgdb.connect(config) as conn:
        conn.execute(
            """
            DELETE FROM learning_tasks
            WHERE plan_id IN (SELECT id FROM learning_plans WHERE user_id = %s)
            """,
            (user_id,),
        )
        cur = conn.execute(
            "DELETE FROM learning_plans WHERE user_id = %s", (user_id,)
        )
        return cur.rowcount


def list_plans(config: Config, user_id: str, limit: int = 50) -> list[dict]:
    """列出某用户的计划摘要（供阶段 8 演示页/聚合读取）。"""
    with pgdb.connect(config) as conn:
        conn.row_factory = dict_row
        rows = conn.execute(
            """
            SELECT id, user_id, goal, source_role, status, metrics_json, is_llm_enhanced, created_at
            FROM learning_plans
            WHERE user_id = %s
            ORDER BY created_at DESC
            LIMIT %s
            """,
            (user_id, limit),
        ).fetchall()
    out = []
    for r in rows:
        metrics = r["metrics_json"] or {}
        total = int(metrics.get("total_tasks") or 0)
        done = int(metrics.get("done_tasks") or 0)
        out.append(
            {
                "plan_id": r["id"],
                "user_id": r["user_id"],
                "goal": r["goal"] or "",
                "source_role": r["source_role"] or "",
                "status": r["status"],
                "total_tasks": total,
                "done_tasks": done,
                "progress": round(done / total, 2) if total else 0.0,
                "is_llm_enhanced": bool(r["is_llm_enhanced"]),
                "created_at": r["created_at"],
            }
        )
    return out


def transition_task(config: Config, plan_id: str, task_id: str, action: str) -> LearningTask:
    """执行任务状态流转。非法流转抛 ValueError；返回更新后的任务。"""
    with pgdb.connect(config) as conn:
        conn.row_factory = dict_row
        row = conn.execute(
            "SELECT * FROM learning_tasks WHERE id = %s AND plan_id = %s",
            (task_id, plan_id),
        ).fetchone()
        if not row:
            raise ValueError("学习任务不存在")

        current = row["status"]
        target = _transition_target(current, action)
        now = _now()
        if target == TASK_DOING:
            conn.execute(
                """
                UPDATE learning_tasks
                SET status=%s, started_at=%s, updated_at=now()
                WHERE id=%s AND plan_id=%s
                """,
                (target, now, task_id, plan_id),
            )
        elif target == TASK_DONE:
            conn.execute(
                """
                UPDATE learning_tasks
                SET status=%s, finished_at=%s, updated_at=now()
                WHERE id=%s AND plan_id=%s
                """,
                (target, now, task_id, plan_id),
            )
        else:  # 幂等：目标与当前一致
            current = action

        out = {
            "id": task_id,
            "skill_id": row["skill_id"],
            "title": row["title"],
            "status": target,
        }
        return _mark_done_plan(config, plan_id, out)


def _transition_target(current: str, action: str) -> str:
    expected = TASK_DOING if action == "start" else TASK_DONE
    if expected == current:
        return expected  # 幂等
    if expected in VALID_TRANSITIONS.get(current, set()):
        return expected
    raise ValueError(f"非法状态流转：{current} ——{action}→ {expected}")


def set_task_status(config: Config, plan_id: str, task_id: str, status: str) -> LearningTask:
    """直接设置任务状态（手动勾选「已掌握」用；任意合法状态，可来回切换）。"""
    with pgdb.connect(config) as conn:
        conn.row_factory = dict_row
        row = conn.execute(
            "SELECT * FROM learning_tasks WHERE id = %s AND plan_id = %s",
            (task_id, plan_id),
        ).fetchone()
        if not row:
            raise ValueError("学习任务不存在")

        now = _now()
        started_at = now if status == TASK_DOING else row["started_at"]
        finished_at = now if status == TASK_DONE else None
        conn.execute(
            """
            UPDATE learning_tasks
            SET status=%s, started_at=%s, finished_at=%s, updated_at=now()
            WHERE id=%s AND plan_id=%s
            """,
            (status, started_at, finished_at, task_id, plan_id),
        )
        out = {
            "id": task_id,
            "skill_id": row["skill_id"],
            "title": row["title"],
            "status": status,
        }
    return _mark_done_plan(config, plan_id, out)


def _mark_done_plan(config: Config, plan_id: str, task_out: dict) -> LearningTask:
    """状态流转后按需把 plan 置为 finished，并回读最新 metrics 以保持 task 返回准确。"""
    plan = load_plan(config, plan_id)
    if plan and plan.status == PLAN_IN_PROGRESS and plan.metrics.done_tasks >= plan.metrics.total_tasks:
        with pgdb.connect(config) as conn:
            conn.execute(
                "UPDATE learning_plans SET status=%s, updated_at=now() WHERE id=%s",
                (PLAN_FINISHED, plan_id),
            )
    return LearningTask(
        task_id=task_out["id"],
        skill_id=task_out.get("skill_id") or "",
        title=task_out.get("title") or "",
        status=task_out["status"],
    )


def _refresh_status(config: Config, plan: LearningPlan) -> None:
    """重算 plan.status（全部任务 done ⇒ finished）。"""
    if plan.metrics.total_tasks and plan.metrics.done_tasks >= plan.metrics.total_tasks:
        plan.status = PLAN_FINISHED
    # 修复被外部提前置为 finished 的情况不做回写（保持简单、只读计算）
    if plan.status != PLAN_FINISHED and plan.metrics.done_tasks < plan.metrics.total_tasks:
        plan.status = PLAN_IN_PROGRESS