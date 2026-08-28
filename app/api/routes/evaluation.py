"""阶段 6 实践任务 / 能力评估接口（HTTP 入出；业务在 app/practice、app/evaluation 层）。

POST /api/v1/practice/generate       -- LearningTask → PracticePlan
GET  /api/v1/practice/<practice_id>  -- 查询实践计划
POST /api/v1/evaluation/artifact     -- 上传代码片段
POST /api/v1/evaluation/evaluate     -- 评估 → 回写画像+再规划
"""
from __future__ import annotations

from flask import Blueprint, current_app, request

from app.api.errors import (
    CODE_EVALUATION,
    CODE_JSON_INVALID,
    CODE_PRACTICE,
    CODE_PRACTICE_NOT_FOUND,
    CODE_VALIDATION,
    APIError,
    ok_response,
)
from app.api.schemas import first_validation_error
from app.evaluation import service as eval_service
from app.evaluation.schemas import ArtifactUploadRequest, EvaluationRequest
from app.practice import planner as practice_planner
from app.practice import store as practice_store
from app.practice.schemas import PracticeCreateRequest

eval_bp = Blueprint("evaluation", __name__)
practice_bp = Blueprint("practice", __name__)


def _config():
    return current_app.extensions["skillmap"]["config"]


def _ensure_db():
    if not _config().database_url:
        raise APIError(CODE_EVALUATION, "实践/评估不可用：未配置 DATABASE_URL", 503)


def _validate(raw, model):
    try:
        return model.model_validate(raw)
    except Exception as exc:  # noqa: BLE001
        raise APIError(CODE_VALIDATION, first_validation_error(exc), 422)


# ---------------- Practice ----------------

@practice_bp.post("/api/v1/practice/generate")
def practice_generate():
    raw = request.get_json(silent=True)
    if raw is None:
        raise APIError(CODE_JSON_INVALID, "请求体必须为合法 JSON", 400)
    req = _validate(raw, PracticeCreateRequest)
    _ensure_db()
    try:
        plan = practice_planner.generate(_config(), req)
    except ValueError as exc:
        raise APIError(CODE_VALIDATION, str(exc), 422)
    except Exception:  # noqa: BLE001
        current_app.logger.exception("实践任务生成失败")
        raise APIError(CODE_PRACTICE, "实践任务生成失败", 500)
    # 阶段 7：沉淀经历记忆（best-effort）
    from app.memory.service import record_event_best_effort

    record_event_best_effort(
        _config(), req.user_id, "practice_created",
        ref_ids={"plan_id": plan.plan_id, "task_id": req.task_id},
        summary=f"生成实践任务：{req.skill_id}",
        payload={"skill_id": req.skill_id},
    )
    return ok_response(plan.model_dump(mode="json"))


@practice_bp.get("/api/v1/practice/<practice_id>")
def practice_get(practice_id: str):
    _ensure_db()
    plan = practice_store.load_practice(_config(), practice_id)
    if plan is None:
        raise APIError(CODE_PRACTICE_NOT_FOUND, "实践任务不存在", 404)
    return ok_response(plan.model_dump(mode="json"))


# ---------------- Evaluation ----------------

@eval_bp.post("/api/v1/evaluation/artifact")
def evaluation_artifact():
    raw = request.get_json(silent=True)
    if raw is None:
        raise APIError(CODE_JSON_INVALID, "请求体必须为合法 JSON", 400)
    req = _validate(raw, ArtifactUploadRequest)
    _ensure_db()
    try:
        result = eval_service.ingest_snippet(_config(), req)
    except Exception:  # noqa: BLE001
        current_app.logger.exception("代码片段入库失败")
        raise APIError(CODE_EVALUATION, "代码片段入库失败", 500)
    return ok_response(result)


@eval_bp.post("/api/v1/evaluation/evaluate")
def evaluation_evaluate():
    raw = request.get_json(silent=True)
    if raw is None:
        raise APIError(CODE_JSON_INVALID, "请求体必须为合法 JSON", 400)
    req = _validate(raw, EvaluationRequest)
    _ensure_db()
    try:
        report = eval_service.run_evaluation(_config(), req)
    except ValueError as exc:
        raise APIError(CODE_VALIDATION, str(exc), 422)
    except Exception:  # noqa: BLE001
        current_app.logger.exception("能力评估失败")
        raise APIError(CODE_EVALUATION, "能力评估失败", 500)
    # 阶段 7：沉淀经历记忆（best-effort）
    from app.memory.service import record_event_best_effort

    record_event_best_effort(
        _config(), req.user_id, "evaluation_done",
        ref_ids={"practice_id": report.practice_id, "evaluation_id": report.evaluation_id},
        summary=f"能力评估完成 overall={report.overall_score}",
        payload={"overall_score": report.overall_score, "replanned": report.replanned},
    )
    return ok_response(report.model_dump(mode="json"))