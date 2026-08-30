"""TeachingAgent —— 针对单个 LearningTask 生成 AI 技术教学并支持多轮互动。

职责边界（对齐「PlannerAgent 管学什么，TeachingAgent 管怎么教」）：
- 输入：完整 LearningTask（goal / skill / task_title / learning_objective / acceptance_criteria /
  execution_steps）——我们不重新生成学习目标，任务本身就是目标。
- 输出：TeachingSession —— opening 开场 + 结构化 content（concepts / examples / exercises），
  以及后续多轮互动（讲解 → 提问 → 判断 → 继续/重讲）。

LLM 结构化输出沿用 learning_plan_agent 的「prompt → 抽取 JSON → Pydantic 校验」模式；
LLM 关闭/失败时给出规则兜底，保证接口不 500。
"""
from __future__ import annotations

import json
import logging

from pydantic import BaseModel, Field

from app.config import Config
from app.teaching.schemas import (
    ROLE_AI,
    ROLE_USER,
    TeachingContent,
    TeachingExample,
    TeachingExercise,
    TeachingRequest,
    TeachingSession,
    TeachingTurn,
    TeachingConcept,
)

logger = logging.getLogger(__name__)


# ---------------- LLM 结构化输出契约 ----------------

class _LLMContent(BaseModel):
    concepts: list[TeachingConcept] = Field(default_factory=list)
    examples: list[TeachingExample] = Field(default_factory=list)
    exercises: list[TeachingExercise] = Field(default_factory=list)


class _LLMStart(BaseModel):
    opening: str = ""
    content: _LLMContent = Field(default_factory=_LLMContent)


class _LLMTurn(BaseModel):
    message: str
    mode: str = "explain"   # explain | question | exercise | verify


# ---------------- 生成教学会话 ----------------

def generate(config: Config, req: TeachingRequest) -> TeachingSession:
    """先生成首节教学内容（opening + 结构化 content），再存入会话内存。"""
    data = _llm_start(config, req) or _rule_start(req)
    session = TeachingSession(
        plan_id=req.plan_id,
        task_id=req.task_id,
        user_id=req.user_id,
        title=f"{req.skill_name or req.task_title} 学习",
        learning_objective=req.learning_objective or req.task_title,
        acceptance_criteria=req.acceptance_criteria or "",
        opening=data["opening"],
        content=data["content"],
    )
    return session


# ---------------- 多轮互动 ----------------

def continue_turn(config: Config, session: TeachingSession, user_message: str) -> TeachingTurn:
    """把用户消息（含「我理解了 / 继续 / 给我出题」等）交给 LLM，返回一轮 AI 应答。"""
    data = _llm_turn(config, session, user_message) or _rule_turn(user_message)
    return TeachingTurn(
        role=ROLE_AI,
        message=data["message"],
        mode=data["mode"],
    )


# ---------------- LLM ----------------

def _llm(config: Config, temperature: float):
    from langchain_core.prompts import ChatPromptTemplate
    from langchain_openai import ChatOpenAI

    model = ChatOpenAI(
        model=config.llm_model,
        base_url=config.llm_base_url,
        api_key=config.llm_api_key,
        temperature=temperature,
    )

    def invoke(table: str, **kwargs) -> dict:
        chain = ChatPromptTemplate.from_messages(
            [
                ("system", table),
                ("human", kwargs.pop("human", "").strip()),
            ]
        ) | model
        res = chain.invoke(kwargs)
        text = (res.content if hasattr(res, "content") else str(res)).strip()
        return json.loads(_extract_json(text))

    return invoke


def _llm_start(config: Config, req: TeachingRequest) -> dict | None:
    if not config.llm_enabled:
        return None
    try:
        data = _llm(config, 0.4)(
            _START_SYSTEM_PROMPT,
            human=_start_human(req),
        )
        parsed = _LLMStart(
            opening=data.get("opening") or "",
            content=_LLMContent(**data.get("content") or {}),
        )
        return {
            "opening": parsed.opening,
            "content": parsed.content,
        }
    except Exception:  # noqa: BLE001
        logger.warning("TeachingAgent 首节生成失败，回退规则兜底", exc_info=True)
        return None


def _llm_turn(config: Config, session: TeachingSession, user_message: str) -> dict | None:
    if not config.llm_enabled:
        return None
    try:
        data = _llm(config, 0.6)(
            _TURN_SYSTEM_PROMPT,
            human=_turn_human(session, user_message),
        )
        parsed = _LLMTurn(message=str(data.get("message") or "")[:1200], mode=data.get("mode") or "explain")
        return {"message": parsed.message, "mode": parsed.mode}
    except Exception:  # noqa: BLE001
        logger.warning("TeachingAgent 多轮应答失败，回退规则兜底", exc_info=True)
        return None


def _extract_json(text: str) -> str:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = stripped.strip("`")
        if stripped.startswith("json"):
            stripped = stripped[4:]
    start = stripped.find("{")
    end = stripped.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("LLM 未返回合法 JSON")
    return stripped[start : end + 1]


# ---------------- 规则兜底 ----------------

def _rule_start(req: TeachingRequest) -> dict:
    name = req.skill_name or req.task_title
    return {
        "opening": f"我们开始学习「{name}」。\n本次目标：{req.learning_objective or req.task_title}。\n"
        f"学完后，你应该能达成：{req.acceptance_criteria or '掌握' + name + '并能完成一次可运行验证'}。",
        "content": TeachingContent(
            concepts=[
                TeachingConcept(title="核心概念", explanation=f"围绕 {name} 的核心概念、作用与适用场景展开。"),
                TeachingConcept(title="工作原理", explanation="说明 {name} 在父框架上下文中的运作机制与关键要素。".format(name=name)),
            ],
            examples=[
                TeachingExample(title="最小示例", explanation="给出一个可运行的最小示例，观察行为/输出变化。", code="# 最小示例代码占位\n"),
            ],
            exercises=[
                TeachingExercise(
                    title="练习与验收",
                    instruction=f"参照示例，独立完成与 {name} 相关的一次小实验/小实现，并验证结果符合预期。",
                    expected_result=req.acceptance_criteria,
                )
            ],
        ),
    }


def _rule_turn(user_message: str) -> dict:
    return {
        "message": "（离线兜底）我已收到你的问题，当前无 LLM 可用。请稍后再试，或先按上面给出的概念、示例与练习自主实践。",
        "mode": "explain",
    }


# ---------------- Prompt ----------------

def _start_human(req: TeachingRequest) -> str:
    steps = "\n".join(f"- {s.title or s.action}" for s in (req.execution_steps or [])) or "\n".join(
        f"- {s}" for s in (req.steps or [])
    )
    return (
        f"计划目标：{req.goal}\n"
        f"技能：{req.skill_name}（id: {req.skill_id}）\n"
        f"任务标题（学习目标）：{req.task_title}\n"
        f"学习目标要点：{req.learning_objective}\n"
        f"验收标准：{req.acceptance_criteria}\n"
        f"执行步骤：\n{steps}\n\n"
        "只输出一段合法 JSON（不要 markdown 代码块），结构如下：\n"
        '{"opening":"1~2 句口语开场并明确本次目标",'
        '"content":{"concepts":[{"title":"概念名","explanation":"概念讲解"}],'
        '"examples":[{"title":"示例名","explanation":"讲解","code":"可选，代码"}],'
        '"exercises":[{"title":"练习名","instruction":"做什么","expected_result":"预期结果","hint":"可选提示"}]}}'
    )


def _turn_human(session: TeachingSession, user_message: str) -> str:
    history = "\n".join(f"{'AI' if t.role == ROLE_AI else '用户'}：{t.message}" for t in session.turns[-4:])
    return (
        f"本次任务（学习目标）：{session.title} / {session.learning_objective}\n"
        f"验收标准：{session.acceptance_criteria}\n"
        f"本节已讲授概念：{', '.join(c.title for c in session.content.concepts)}\n"
        f"本节示例：{', '.join(e.title for e in session.content.examples)}\n"
        f"练习：{', '.join(e.title for e in session.content.exercises)}\n\n"
        f"最近对话记录：\n{history}\n\n"
        f"用户本轮消息：{user_message}\n\n"
        "只输出一段合法 JSON：{\"message\":\"你的讲解/回答（按需引用上面的概念、示例、练习）\","
        '"mode":"explain 或 question 或 exercise 或 verify"}。'
    )


# ---------------- Prompt 表 ----------------

_START_SYSTEM_PROMPT = """你是 SkillPilot 的 TeachingAgent——一名耐心的技术讲师，负责针对「一个学习任务」开展 AI 技术教学。

要求：
1. opening：1~2 句口语开场，向用户点明本次目标，不啰嗦、不加 markdown 标题。
2. concepts：拆解 3~6 个核心概念，用通俗语言讲清「是什么、为什么、怎么用（在父框架上下文中的位置）」，
   并针对该技能的 skill_type（机制/API/框架/模式等）匹配恰当讲解方式。
3. examples：给 1~3 个紧密围绕本任务的可运行示例；能贴代码就贴真实可运行的代码。
4. exercises：给 1~3 个贴合验收标准的练习，能引导用户动手验证，而不是只有理论。
5. 全程围绕给定的「学习目标 / 验收标准 / 执行步骤」，不要跑题到讲别的技能，也不要重新生成一整份学习计划。
禁止编造不存在的 API；不确定的用法用「...」占位并说明。"""

_TURN_SYSTEM_PROMPT = """你是 SkillPilot 的 TeachingAgent，正在与用户针对同一个学习任务进行多轮教学互动。

结合已讲授的内容、示例、练习与最近对话，回应用户。
- 用户说「我理解了/懂了」→ 进入下一部分或给出小结，并可用 mode=question 追问一道理解题。
- 用户说「继续」→ mode=explain，讲下一个要点。
- 用户说「给我出题」→ mode=exercise，出一道贴合验收标准的练习题。
- 用户说「完成了/已掌握」→ mode=verify，给出验证方式并判断是否接近达成验收标准。
- 用户提问 → 用上一节提到的概念/示例解答，必要时换一种比喻。

回答紧扣本任务，不需要展开到整个计划；若用户表达已掌握，可在结尾自然地把话引向「可到任务列表将该小目标勾选完成」。"""