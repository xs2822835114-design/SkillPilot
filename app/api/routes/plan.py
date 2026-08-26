"""阶段 5 学习规划 / Todo 接口（HTTP 入出；业务在 app/todo 层）。

POST /api/v1/plan/generate                       -- 生成学习计划（A 传报告 / B 自算缺口）
GET  /api/v1/plan/<plan_id>                       -- 查询/恢复计划
POST /api/v1/plan/<plan_id>/replan                -- 局部重规划（保留 done 任务）
POST /api/v1/plan/<plan_id>/tasks/<task_id>/transition -- 任务状态流转 start/complete
"""
from __future__ import annotations

from flask import Blueprint, current_app, request

from app.api.errors import (
    CODE_JSON_INVALID,
    CODE_PLAN,
    CODE_PLAN_NOT_FOUND,
    CODE_VALIDATION,
    APIError,
    ok_response,
)
from app.api.schemas import first_validation_error
from app.todo import planner, todo_store
from app.todo.schemas import PlanRequest, ReplanRequest, TaskTransitionRequest

plan_bp = Blueprint("plan", __name__)


def _config():
    return current_app.extensions["skillmap"]["config"]


def _ensure_db():
    cfg = _config()
    if not cfg.database_url:
        raise APIError(CODE_PLAN, "学习计划不可用：未配置 DATABASE_URL", 503)


@plan_bp.post("/api/v1/plan/generate")
def plan_generate():
    raw = request.get_json(silent=True)
    if raw is None:
        raise APIError(CODE_JSON_INVALID, "请求体必须为合法 JSON", 400)
    req = _validate(raw, PlanRequest)
    try:
        req.ensure_source()
    except ValueError as exc:
        raise APIError(CODE_VALIDATION, str(exc), 422)
    _ensure_db()
    try:
        plan = planner.generate(_config(), req)
    except ValueError as exc:
        raise APIError(CODE_VALIDATION, str(exc), 422)
    except Exception:  # noqa: BLE001
        current_app.logger.exception("学习计划生成失败")
        raise APIError(CODE_PLAN, "学习计划生成失败", 500)
    # 阶段 7：沉淀经历记忆（best-effort）
    _record_plan_event(_config(), req.user_id, "plan_generated", plan.plan_id, len(plan.phases))
    return ok_response(plan.model_dump())


@plan_bp.get("/api/v1/plan/<plan_id>")
def plan_get(plan_id: str):
    _ensure_db()
    plan = todo_store.load_plan(_config(), plan_id)
    if plan is None:
        raise APIError(CODE_PLAN_NOT_FOUND, "学习计划不存在", 404)
    return ok_response(plan.model_dump())


@plan_bp.get("/api/v1/plan/list")
def plan_list():
    """阶段 8：列出某用户的计划摘要，供演示页选择计划。"""
    user_id = (request.args.get("user_id", "") or "").strip()
    if not user_id:
        raise APIError(CODE_VALIDATION, "user_id 必填", 422)
    _ensure_db()
    limit = request.args.get("limit", type=int) or 50
    try:
        plans = todo_store.list_plans(_config(), user_id, limit)
    except Exception:  # noqa: BLE001
        current_app.logger.exception("学习计划列表读取失败")
        raise APIError(CODE_PLAN, "学习计划列表读取失败", 500)
    return ok_response(plans)


@plan_bp.post("/api/v1/plan/<plan_id>/replan")
def plan_replan(plan_id: str):
    raw = request.get_json(silent=True)
    if raw is None:
        raise APIError(CODE_JSON_INVALID, "请求体必须为合法 JSON", 400)
    req = _validate(raw, ReplanRequest)
    _ensure_db()
    try:
        plan = planner.replan(_config(), plan_id, req)
    except ValueError as exc:
        raise APIError(CODE_VALIDATION, str(exc), 422)
    except Exception:  # noqa: BLE001
        current_app.logger.exception("学习计划重规划失败")
        raise APIError(CODE_PLAN, "学习计划重规划失败", 500)
    # 阶段 7：沉淀经历记忆（best-effort）
    _record_plan_event(_config(), plan.user_id, "plan_replanned", plan.plan_id, len(plan.phases))
    return ok_response(plan.model_dump())


@plan_bp.post("/api/v1/plan/<plan_id>/tasks/<task_id>/transition")
def task_transition(plan_id: str, task_id: str):
    raw = request.get_json(silent=True)
    if raw is None:
        raise APIError(CODE_JSON_INVALID, "请求体必须为合法 JSON", 400)
    req = _validate(raw, TaskTransitionRequest)
    _ensure_db()
    try:
        task = todo_store.transition_task(_config(), plan_id, task_id, req.action)
    except ValueError as exc:
        raise APIError(CODE_VALIDATION, str(exc), 422)
    except Exception:  # noqa: BLE001
        current_app.logger.exception("任务状态流转失败")
        raise APIError(CODE_PLAN, "任务状态流转失败", 500)
    return ok_response(task.model_dump())


def _validate(raw, model):
    try:
        return model.model_validate(raw)
    except Exception as exc:  # noqa: BLE001
        raise APIError(CODE_VALIDATION, first_validation_error(exc), 422)


def _record_plan_event(cfg, user_id: str, event_type: str, plan_id: str, phase_count: int) -> None:
    """best-effort：沉淀学习计划经历记忆。"""
    if not user_id:
        return
    from app.memory.service import record_event_best_effort

    record_event_best_effort(
        cfg, user_id, event_type,
        ref_ids={"plan_id": plan_id},
        summary=f"学习计划{'重规划' if 're' in event_type else '已生成'}：{phase_count} 个阶段",
        payload={"phase_count": phase_count},
    )