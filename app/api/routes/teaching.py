"""AI 技术教学接口（TeachingAgent，阶段 5 三级结构第三级）。

POST /api/v1/plan/<plan_id>/tasks/<task_id>/teach            -- 启动教学，返回结构化 TeachingSession
POST /api/v1/plan/<plan_id>/tasks/<task_id>/teach/stream      -- SSE 流式首节教学（meta → delta* → done）
POST /api/v1/teaching/<session_id>/message                    -- 多轮互动（我理解了/继续/给我出题/提问）

前三接口都要求计划已存在（DB）；教学会话本身在内存按 session_id 恢复。
"""
from __future__ import annotations

from flask import Blueprint, Response, current_app, request, stream_with_context

from app.api.errors import (
    CODE_JSON_INVALID,
    CODE_PLAN,
    CODE_PLAN_NOT_FOUND,
    CODE_TEACHING,
    CODE_TEACHING_NOT_FOUND,
    CODE_VALIDATION,
    APIError,
    ok_response,
)
from app.api.schemas import first_validation_error
from app.teaching.schemas import ROLE_USER, TeachingMessageRequest, TeachingRequest, TeachingStartRequest, TeachingTurn

teaching_bp = Blueprint("teaching", __name__)


def _config():
    return current_app.extensions["skillmap"]["config"]


def _ensure_db():
    cfg = _config()
    if not cfg.database_url:
        raise APIError(CODE_PLAN, "学习计划不可用：未配置 DATABASE_URL", 503)


def _load_task(plan_id: str, task_id: str):
    """加载计划并定位任务，构建 TeachingRequest 输入。"""
    from app.todo import todo_store

    plan = todo_store.load_plan(_config(), plan_id)
    if plan is None:
        raise APIError(CODE_PLAN_NOT_FOUND, "学习计划不存在", 404)
    for phase in plan.phases:
        for task in phase.tasks:
            if task.task_id == task_id:
                return TeachingRequest(
                    plan_id=plan_id,
                    task_id=task_id,
                    user_id=plan.user_id,
                    goal=plan.goal,
                    skill_id=task.skill_id or "",
                    skill_name="",
                    task_title=task.title or "",
                    learning_objective=task.title or task.acceptance_criteria or "",
                    acceptance_criteria=task.acceptance_criteria or "",
                    execution_steps=list(task.execution_steps or []),
                    steps=list(task.steps or []),
                )
    raise APIError(CODE_PLAN_NOT_FOUND, "学习任务不存在", 404)


def _skill_name(cfg, skill_id: str) -> str:
    if not skill_id:
        return ""
    try:
        from app.knowledge.learning_metadata import classify

        return classify(cfg, skill_id).skill_name or ""
    except Exception:  # noqa: BLE001 - 缺 name 不影响教学，标题回退用任务标题
        return ""


@teaching_bp.post("/api/v1/plan/<plan_id>/tasks/<task_id>/teach")
def teach_start(plan_id: str, task_id: str):
    raw = request.get_json(silent=True)
    if raw is None:
        raise APIError(CODE_JSON_INVALID, "请求体必须为合法 JSON", 400)
    try:
        TeachingStartRequest.model_validate(raw)
    except Exception as exc:  # noqa: BLE001 - 保留 start 扩展位
        raise APIError(CODE_VALIDATION, first_validation_error(exc), 422)
    _ensure_db()
    req = _load_task(plan_id, task_id)
    req.skill_name = _skill_name(_config(), req.skill_id)

    from app.teaching import session_store, teaching_agent

    try:
        session = teaching_agent.generate(_config(), req)
    except Exception:  # noqa: BLE001
        current_app.logger.exception("AI 教学生成失败")
        raise APIError(CODE_TEACHING, "AI 教学生成失败", 500)
    session_store.put(session)
    return ok_response(session.model_dump())


@teaching_bp.post("/api/v1/plan/<plan_id>/tasks/<task_id>/teach/stream")
def teach_start_stream(plan_id: str, task_id: str):
    """SSE 流式首节教学：先下发 meta（含任务信息），再流式输出 opening 文本，
    最后 done 携带完整的结构化 TeachingSession（含 session_id，供后续多轮互动用）。"""
    _ensure_db()
    req = _load_task(plan_id, task_id)
    req.skill_name = _skill_name(_config(), req.skill_id)

    from app.teaching import session_store, teaching_agent

    def generate():
        try:
            session = teaching_agent.generate(_config(), req)
            session_store.put(session)
            yield _sse("meta", {"task_id": task_id, "title": req.task_title})
        except Exception:  # noqa: BLE001
            current_app.logger.warning("AI 教学流式生成异常", exc_info=True)
            yield _sse("error", {"message": "AI 教学生成失败，请重试"})
            return
        for i in range(0, len(session.opening), _CHUNK):
            yield _sse("delta", {"text": session.opening[i : i + _CHUNK]})
        yield _sse("done", session.model_dump())

    return Response(stream_with_context(generate()), content_type="text/event-stream")


@teaching_bp.post("/api/v1/teaching/<session_id>/message")
def teach_message(session_id: str):
    from app.teaching import session_store, teaching_agent

    session = session_store.get(session_id)
    if session is None:
        raise APIError(CODE_TEACHING_NOT_FOUND, "教学会话不存在或已过期", 404)

    raw = request.get_json(silent=True)
    if raw is None:
        raise APIError(CODE_JSON_INVALID, "请求体必须为合法 JSON", 400)
    try:
        req = TeachingMessageRequest.model_validate(raw)
    except Exception as exc:  # noqa: BLE001
        raise APIError(CODE_VALIDATION, first_validation_error(exc), 422)

    session.append(TeachingTurn(role=ROLE_USER, message=req.message, mode="question"))
    try:
        turn = teaching_agent.continue_turn(_config(), session, req.message)
    except Exception:  # noqa: BLE001
        current_app.logger.exception("AI 教学多轮应答失败")
        raise APIError(CODE_TEACHING, "AI 教学多轮应答失败", 500)
    session.append(turn)
    return ok_response(turn.model_dump())


_CHUNK = 4  # 流式打字机字符数


def _sse(event: str, data: dict) -> str:
    import json

    return f"data: {json.dumps({'type': event, **data}, ensure_ascii=False, default=str)}\n\n"