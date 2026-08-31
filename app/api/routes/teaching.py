"""AI 技术教学接口（TeachingAgent，阶段 5 三级结构第三级）。

POST /api/v1/plan/<plan_id>/tasks/<task_id>/teach            -- 启动教学，返回结构化 TeachingSession
POST /api/v1/plan/<plan_id>/tasks/<task_id>/teach/stream      -- SSE 流式首节教学（meta → delta* → done）
POST /api/v1/teaching/<session_id>/message                    -- 多轮互动（我理解了/继续/给我出题/提问）

前三接口都要求计划已存在（DB）；教学会话本身在内存按 session_id 恢复。
"""
from __future__ import annotations

import time

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
from app.teaching.schemas import ROLE_USER, TeachingContent, TeachingMessageRequest, TeachingRequest, TeachingSession, TeachingStartRequest, TeachingTurn

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

    # 既有会话按 user_id+task_id 稳定恢复：同一任务再次「开始学习」返回历史会话，而非新建空会话
    existing = session_store.load_by_task(_config(), req.user_id, req.task_id)
    if existing is not None:
        return ok_response(existing.model_dump())

    try:
        session = teaching_agent.generate(_config(), req)
    except Exception:  # noqa: BLE001
        current_app.logger.exception("AI 教学生成失败")
        raise APIError(CODE_TEACHING, "AI 教学生成失败", 500)
    session_store.save(_config(), session)
    return ok_response(session.model_dump())


@teaching_bp.post("/api/v1/plan/<plan_id>/tasks/<task_id>/teach/stream")
def teach_start_stream(plan_id: str, task_id: str):
    """SSE 流式首节教学（性能优化版）。

    关键时序（目标是「点击 → 尽快看到第一段内容」）：
    1. 同步段只做轻量数据库准备（计划/技能名/会话存在性），不调 LLM；
    2. ``meta`` 首帧**在阻塞业务前立即下发**，让前端弹窗瞬间拿到任务信息；
    3. 新会话：opening 走真实 ``astream`` 逐 token 下发（首 token 即显示），
       结构化 content（concepts/examples/exercises）放进**后台线程**与开场并行生成；
    4. 恢复会话：不做任何 LLM 调用，直接下发 done 回显历史（仅一次 DB 读取）。
    """
    t_route = time.perf_counter()
    _ensure_db()
    req = _load_task(plan_id, task_id)
    req.skill_name = _skill_name(_config(), req.skill_id)
    current_app.logger.info(
        "[Teaching] stream entry plan=%s task=%s sync_prep=%.0fms",
        plan_id, task_id, (time.perf_counter() - t_route) * 1000,
    )

    from app.teaching import session_store, teaching_agent

    cfg = _config()  # 捕获 Config（后台线程无 Flask app context，需直接传对象）

    # 稳定恢复：同一任务已有会话则复用（含历史回合），否则进入新建 + 流式生成路径
    recovered = session_store.load_by_task(cfg, req.user_id, req.task_id)
    current_app.logger.info(
        "[Teaching] session_load done recovered=%s %.0fms",
        recovered is not None, (time.perf_counter() - t_route) * 1000,
    )

    def generate():
        # 恢复路径：无任何 LLM 调用，仅回传历史快照
        if recovered is not None:
            yield _sse("meta", {"task_id": task_id, "title": req.task_title})
            yield _sse("done", recovered.model_dump())
            return

        t0 = time.perf_counter()
        try:
            yield _sse("meta", {"task_id": task_id, "title": req.task_title})
            current_app.logger.info("[Teaching] meta sent +%.0fms", (time.perf_counter() - t0) * 1000)

            # 真实流式开场：逐 token 下发，首 token 到达即显示
            t_llm = time.perf_counter()
            opening_parts: list[str] = []
            first_token_ms = None
            for tok in teaching_agent.stream_start_opening(cfg, req):
                if first_token_ms is None:
                    first_token_ms = (time.perf_counter() - t_llm) * 1000
                opening_parts.append(tok)
                yield _sse("delta", {"text": tok})
            opening = "".join(opening_parts)
            current_app.logger.info(
                "[Teaching] opening first_token=%.0fms total=%.0fms chars=%d",
                first_token_ms or 0, (time.perf_counter() - t_llm) * 1000, len(opening),
            )

            # 结构化内容按「概念→示例→练习」逐类生成即推（content_part），不等全部 JSON，
            # 前端逐类增量补齐，避免一次生成 20s+ 才看到任何结构化内容。
            concepts, examples, exercises = [], [], []
            for kind, items in teaching_agent.generate_content_parts(cfg, req):
                bucket = {"concepts": concepts, "examples": examples, "exercises": exercises}[kind]
                bucket.extend(items)
                yield _sse("content_part", {"kind": kind, "items": [i.model_dump() for i in items]})
                current_app.logger.info(
                    "[Teaching] content_part %s n=%d +%.0fms", kind, len(items), (time.perf_counter() - t0) * 1000,
                )
            content = TeachingContent(concepts=concepts, examples=examples, exercises=exercises)
            current_app.logger.info(
                "[Teaching] content all ready +%.0fms", (time.perf_counter() - t0) * 1000,
            )

            session = TeachingSession(
                plan_id=req.plan_id,
                task_id=req.task_id,
                user_id=req.user_id,
                title=f"{req.skill_name or req.task_title} 学习",
                learning_objective=req.learning_objective or req.task_title,
                acceptance_criteria=req.acceptance_criteria or "",
                opening=opening,
                content=content,
            )
            session_store.save(cfg, session)
            current_app.logger.info(
                "[Teaching] session saved +%.0fms -> done", (time.perf_counter() - t0) * 1000,
            )
            yield _sse("done", session.model_dump())
        except Exception as exc:  # noqa: BLE001
            current_app.logger.warning("AI 教学流式生成异常（已回退）", exc_info=True)
            try:
                yield _sse("error", {"message": "AI 教学准备失败，请重试"})
            except Exception:  # noqa: BLE001 - 客户端已断开则静默
                pass

    return Response(stream_with_context(generate()), content_type="text/event-stream")


@teaching_bp.post("/api/v1/teaching/<session_id>/message")
def teach_message(session_id: str):
    from app.teaching import session_store, teaching_agent

    session = session_store.load(_config(), session_id)
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
    # 先把用户消息落库——即使后续 LLM 失败，也不丢失该条输入、且会话仍可继续
    session_store.save(_config(), session)
    try:
        turn = teaching_agent.continue_turn(_config(), session, req.message)
    except Exception:  # noqa: BLE001
        current_app.logger.exception("AI 教学多轮应答失败")
        raise APIError(CODE_TEACHING, "AI 教学多轮应答失败，你的问题已记录，可稍后重试", 500)
    session.append(turn)
    # 每轮互动都落库，保证关闭窗口 / 重启后可恢复历史
    session_store.save(_config(), session)
    return ok_response(turn.model_dump())


@teaching_bp.get("/api/v1/teaching/<session_id>/history")
def teach_history(session_id: str):
    """加载既有学习会话完整快照（opening / content / turns / status），供前端恢复渲染。"""
    from app.teaching import session_store

    session = session_store.load(_config(), session_id)
    if session is None:
        raise APIError(CODE_TEACHING_NOT_FOUND, "教学会话不存在", 404)
    return ok_response(session.model_dump())


_CHUNK = 4  # 流式打字机字符数（已废弃，保留兼容）


def _sse(event: str, data: dict) -> str:
    import json

    return f"data: {json.dumps({'type': event, **data}, ensure_ascii=False, default=str)}\n\n"