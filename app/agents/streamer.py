"""阶段 8 SSE 流式 Agent 输出（agents/streamer）。

流程：复用阶段 1 orchestrator 图计算回复（可靠、有规则兜底）→ 以 SSE 事件流式下发。
- 生成器逐个事件 yield，交给路由的 text/event-stream。
- STREAM_ENABLED=false 时一次性吐完整回复；LLM 不可用/异常时同样走整体兜底，保证"流式失败有降级"。
事件序列：meta → delta* → done；(异常) event:error。
"""
from __future__ import annotations

import logging
import queue
import threading
import time
from typing import Iterator

from app.config import Config

logger = logging.getLogger(__name__)

# 意图 → 引导路由（Demo 形态：Chat 识别 → 引导到对应页面）
_INTENT_ROUTE = {
    "plan_generation": "plan",
    "tech_learning": "plan",
    "job_search": "plan",
    "chat": "chat",
}

_CHUNK = 3  # 每次下发的字符数（演示打字机效果）


def stream_reply(
    config: Config, user_id: str, thread_id: str, message: str, intent_hint: str | None
) -> Iterator[str]:
    """产出 SSE 文本行序列（不含重试字段）。

    先立刻下发 meta 建立/保持连接；随后：
    1) 用关键词预推断计划意图并**立即**广播 intent(route=plan) 与 plan_building，
       避免画面在计算期间停在默认 chat（用户感知为“卡住”）；
    2) 把图计算放到后台线程，与开场叙述并行，显著缩短等待；
    3) 叙述流式播报完成后，等到计算结束，再增量下发学习计划事件与完成确认。
    """
    # 1) 立即占位 meta：让 fetch/SSE 连接尽快收到首帧
    yield _sse("meta", {"intent": "chat", "route": "chat", "thread_id": thread_id})

    # 预推断计划意图，作为 hint 传给图（保证图计算与流式判断一致）
    plan_intent = (
        intent_hint
        if intent_hint in _PLAN_INTENT_HINTS
        else _plan_intent_kind(message)
    )
    hint = plan_intent or intent_hint
    direct = (
        getattr(config, "learning_plan_mode", "direct") == "direct"
        and bool(plan_intent)
        and getattr(config, "llm_enabled", False)
        and getattr(config, "learning_plan_llm_enabled", True)
    )

    # 2) 立即在后台线程启动图计算，与开场叙述并行（减少等待、不阻塞流式）
    flask_app = None
    try:
        from flask import current_app, has_app_context

        if has_app_context():
            flask_app = current_app._get_current_object()
    except Exception:  # noqa: BLE001
        flask_app = None

    result_q: "queue.Queue" = queue.Queue(maxsize=1)

    def _background_compute() -> None:
        try:
            if flask_app is not None:
                with flask_app.app_context():
                    result_q.put(_compute(config, user_id, thread_id, message, hint))
            else:
                result_q.put(_compute(config, user_id, thread_id, message, hint))
        except Exception as exc:  # noqa: BLE001 - 计算异常放到队列，由主流程降级
            result_q.put(exc)

    threading.Thread(target=_background_compute, daemon=True).start()

    # 3) 立刻广播预推断的计划意图/路由，让 trace 一上来就是 plan 而不是 chat
    pre_intent = plan_intent or intent_hint or "chat"
    if pre_intent != "chat":
        yield _sse("intent", {"intent": pre_intent, "route": _INTENT_ROUTE.get(pre_intent, "chat")})
        yield _sse("plan_building", {"message": "正在为你生成分阶段学习计划…"})

    # 4) 开场叙述（前台实时流式），与后台计算并行
    if direct:
        for tok in _stream_narration(config, message):
            yield _sse("delta", {"text": tok})

    # 5) 等到后台计算完成；期间按固定节奏广播 plan_building 心跳，避免看起来卡死
    result = None
    while True:
        try:
            result = result_q.get(timeout=3.0)
            break
        except queue.Empty:
            yield _sse("plan_building", {"message": "正在为你生成分阶段学习计划…"})
            continue

    if isinstance(result, Exception):
        logger.warning("流式图计算异常 user=%s", user_id, exc_info=result)
        for seg in _chunks("抱歉，生成学习计划的过程中发生异常，请稍后再试。", True):
            yield _sse("delta", {"text": seg})
        yield _sse(
            "done",
            {
                "thread_id": thread_id,
                "intent": pre_intent,
                "route": _INTENT_ROUTE.get(pre_intent, "chat"),
                "artifacts": {},
            },
        )
        return

    intent, reply, artifacts = result
    route = _INTENT_ROUTE.get(intent, "chat")
    # 计算完成后的真实意图/路由（可能被 Orchestrator/规则校正）
    yield _sse("intent", {"intent": intent, "route": route})

    # 6) 正式回复：结构化计划事件增量下发（实时可视化），再流式完成确认
    stream = bool(getattr(config, "stream_enabled", True))
    lp = (artifacts or {}).get("learning_plan")
    if isinstance(lp, dict) and lp.get("phases"):
        yield from _yield_plan_events(lp)
    for seg in _stream_reply_segments(reply, stream, direct, config, artifacts):
        yield _sse("delta", {"text": seg})

    yield _sse(
        "done",
        {"thread_id": thread_id, "intent": intent, "route": route, "artifacts": artifacts or {}},
    )


# 计划类意图信号：显式 intent_hint 或消息含学习/规划关键词
_PLAN_INTENT_HINTS = {"tech_learning", "job_search", "plan_generation", "learning_plan"}
# 「想学某技能」→ tech_learning；「生成规划」类措辞 → plan_generation（先匹配更具体的规划词）
_PLAN_HINT_KEYWORDS = {
    "plan_generation": (
        "学习计划", "学习路线", "学习路径", "规划", "学习规划", "路线图", "计划表", "制定计划", "给我一个计划",
    ),
    "tech_learning": (
        "想学", "我要学", "想掌握", "自学", "学一下", "学习", "掌握", "入门", "精通", "提升", "研究", "弄懂", "搞懂",
    ),
}


def _plan_intent_kind(message: str) -> str | None:
    """用关键词推断计划类意图的具体类型（tech_learning / plan_generation）；非计划返回 None。

    与 Orchestrator 的意图识别共用语义，保证流式判断（direct）与图计算结果一致。
    """
    msg = message or ""
    for kind, keywords in _PLAN_HINT_KEYWORDS.items():
        if any(k in msg for k in keywords):
            return kind
    return None


def _llm_chain(config: Config, msgs: list, temperature: float = 0.6):
    from langchain_core.prompts import ChatPromptTemplate
    from langchain_openai import ChatOpenAI

    llm = ChatOpenAI(
        model=config.llm_model,
        base_url=config.llm_base_url,
        api_key=config.llm_api_key,
        temperature=temperature,
    )
    return ChatPromptTemplate.from_messages(msgs) | llm


def _stream_narration(config: Config, message: str) -> Iterator[str]:
    """真实 LLM 流式开场：告诉用户正在分析目标、拆解技能。失败则静默（由正式回复补齐）。"""
    try:
        chain = _llm_chain(
            config,
            [
                (
                    "system",
                    "你是 SkillPilot 的学习规划助手。用户刚表达了学习/规划意图。"
                    "请用 1~2 句口语、不加 markdown、不要加标题，告诉用户：你会先分析他的目标、"
                    "拆解需要掌握的核心技能，然后为他生成一份可执行的分阶段学习计划。"
                    "开头用一个礼貌词如“好的”。不要列出任何具体计划内容。",
                ),
                ("human", "{message}"),
            ],
            temperature=0.6,
        )
        for chunk in chain.stream({"message": message}):
            text = getattr(chunk, "content", None)
            if text:
                yield text
    except Exception:  # noqa: BLE001 - 开场失败不阻断主链路（后面还有正式回复）
        logger.warning("直出计划开场流式失败", exc_info=True)
        return


def _stream_reply_segments(
    reply: str, stream: bool, direct: bool, config: Config, artifacts: dict
) -> Iterator[str]:
    """正式回复分片：开场已流式且拿到了结构化 plan 时，用真实 LLM 把“生成完成”的确认也流式化，保持打字连续。"""
    if not (stream and direct and artifacts.get("learning_plan")):
        yield from _chunks(reply, stream)
        return
    try:
        lp = artifacts["learning_plan"]
        metrics = lp.get("metrics") or {}
        goal = artifacts.get("goal") or lp.get("goal") or ""
        chain = _llm_chain(
            config,
            [
                (
                    "system",
                    "你是 SkillPilot 的学习规划助手。学习计划已生成完毕，请用 1~2 句口语、不加 markdown，"
                    "向用户确认已生成的学习计划概览。必须据实引用以下事实，不得杜撰数字。",
                ),
                ("human", "目标：{goal}\n阶段数：{phases}\n任务数：{tasks}\n预计小时：{hours}"),
            ],
            temperature=0.4,
        )
        got = False
        for chunk in chain.stream(
            {
                "goal": goal,
                "phases": len(lp.get("phases") or []),
                "tasks": metrics.get("total_tasks", 0),
                "hours": metrics.get("total_hours", 0),
            }
        ):
            text = getattr(chunk, "content", None)
            if text:
                got = True
                yield text
        if not got:
            yield from _chunks(reply, stream)
    except Exception:  # noqa: BLE001 - 流式确认失败退回预生成分片
        logger.warning("直出计划确认流式失败，回退分片", exc_info=True)
        yield from _chunks(reply, stream)


def _compute(config: Config, user_id: str, thread_id: str, message: str, intent_hint: str | None):
    """复用 /chat 的图调用得到意图、回复文本与 artifacts（可靠、规则兜底，杜绝流式中途失败）。"""
    from flask import current_app

    ext = current_app.extensions["skillmap"]
    graph = ext["graph"]
    if graph is None:
        from app.orchestrator.graph import build_graph
        from app.persistence.checkpointer import get_checkpointer

        graph = build_graph(config, checkpointer=get_checkpointer(config))
        ext["graph"] = graph

    from app.memory.service import recall_for_user

    try:
        memory_context = recall_for_user(config, user_id)
    except Exception:  # noqa: BLE001 - 长期记忆 best-effort，失败不阻断流式
        logger.warning("加载长期记忆失败 user=%s", user_id, exc_info=True)
        memory_context = {}
    state = graph.invoke(
        {
            "user_id": user_id,
            "thread_id": thread_id,
            "message": message,
            "intent_hint": intent_hint,
            "memory_context": memory_context,
        },
        config={"configurable": {"thread_id": thread_id}},
    )
    messages = state.get("messages") or []
    reply = messages[-1]["content"] if messages else ""
    return state.get("intent") or "chat", reply, state.get("artifacts") or {}


def _yield_plan_events(lp: dict) -> Iterator[str]:
    """把结构化 learning_plan 拆成增量事件下发：plan_phase → plan_task* → plan_complete。

    这里的小间隔是用来营造「计划正在现场生成」的成长感（UI 排版节奏），
    与「对 LLM token 做二次切片模拟打字机」无关——真正的文本 token 已由
    `_stream_narration` / `_stream_reply_segments` 的 `llm.stream()` 实时输出。
    """
    phases = lp.get("phases") or []
    total = 0
    for idx, phase in enumerate(phases):
        pid = phase.get("phase_id") or ""
        yield _sse(
            "plan_phase",
            {"phase_id": pid, "phase": {"phase_id": pid, "title": phase.get("title") or "", "order": phase.get("order", 0)}},
        )
        time.sleep(0.18)  # 阶段的「出生」停顿，让用户感知阶段逐个出现
        for task in phase.get("tasks") or []:
            yield _sse(
                "plan_task",
                {
                    "phase_id": pid,
                    "task": {
                        "task_id": task.get("task_id") or "",
                        "title": task.get("title") or "",
                        "estimated_hours": task.get("estimated_hours", 0),
                        "status": task.get("status", "pending"),
                    },
                },
            )
            total += 1
            time.sleep(0.09)  # 任务的「长出」停顿
        if idx < len(phases) - 1:
            time.sleep(0.12)  # 阶段之间的换气
    yield _sse("plan_complete", {"phase_count": len(phases), "task_count": total})


def _chunks(reply: str, stream: bool) -> Iterator[str]:
    if not reply:
        yield ""
        return
    if not stream:
        yield reply
        return
    for i in range(0, len(reply), _CHUNK):
        yield reply[i : i + _CHUNK]
        time.sleep(0.015)  # 兜底节奏：无 LLM 时对完整文本做分片下发


def _sse(event: str, data: dict) -> str:
    import json

    payload = {"type": event, **data}
    return f"data: {json.dumps(payload, ensure_ascii=False, default=str)}\n\n"