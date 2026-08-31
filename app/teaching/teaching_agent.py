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


# 按类生成时把 LLM 的 {"items":[...]} 逐项映射到领域模型
_KIND_MODEL = {
    "concepts": TeachingConcept,
    "examples": TeachingExample,
    "exercises": TeachingExercise,
}


class _LLMStart(BaseModel):
    opening: str = ""
    content: _LLMContent = Field(default_factory=_LLMContent)


class _LLMTurn(BaseModel):
    message: str
    mode: str = "explain"   # explain | question | exercise | verify


# ---------------- 生成教学会话 ----------------

def generate(config: Config, req: TeachingRequest) -> TeachingSession:
    """先生成首节教学内容（opening + 结构化 content），再存入会话内存。

    提供给非流式 teach_start 使用；SSE 流式首节请使用 stream_start_opening + generate_content，
    它们在 opening 制作流式的同时把结构化 content 放到后台线程并行生成，避免「等完整 JSON」。
    """
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


def stream_start_opening(config: Config, req: TeachingRequest):
    """流式产出首节 opening 文本（真实 token，非对完整串二次切片）。

    - LLM 开启：用 astream 逐 token 产出，首 token 到达即返回，让前端尽快显示；
    - LLM 关闭/失败：回退规则开场并整体吐出（保证接口可用、教学不中断）。
    """
    if not config.llm_enabled:
        yield _rule_opening(req)
        return
    try:
        from langchain_core.prompts import ChatPromptTemplate
        from langchain_openai import ChatOpenAI

        model = ChatOpenAI(
            model=config.llm_model,
            base_url=config.llm_base_url,
            api_key=config.llm_api_key,
            temperature=0.6,
        )
        chain = ChatPromptTemplate.from_messages(
            [
                ("system", _OPENING_SYSTEM_PROMPT),
                ("human", _opening_human(req)),
            ]
        ) | model
        got = False
        for chunk in chain.stream({"task": _task_context(req)}):
            text = getattr(chunk, "content", None)
            if text:
                got = True
                yield text
        if not got:
            yield _rule_opening(req)
    except Exception:  # noqa: BLE001 - 开场流式失败回退规则，不阻断主链路
        logger.warning("stream_start_opening 失败，回退规则开场", exc_info=True)
        yield _rule_opening(req)


def generate_content(config: Config, req: TeachingRequest) -> TeachingContent:
    """仅生成结构化教学内容（concepts / examples / exercises），供 done 携带。

    与 stream_start_opening 并行执行，互不等待；失败或 LLM 关闭时回退规则内容
    （永远返回一个合法的 TeachingContent，绝不让首节 done 缺内容）。
    """
    if not config.llm_enabled:
        return _rule_content(req)
    try:
        data = _llm(config, 0.4)(_CONTENT_SYSTEM_PROMPT, human=_content_human(req))
        inner = _LLMContent(**data.get("content") or {})
        return TeachingContent(
            concepts=list(inner.concepts),
            examples=list(inner.examples),
            exercises=list(inner.exercises),
        )
    except Exception:  # noqa: BLE001
        logger.warning("generate_content 失败，回退规则内容", exc_info=True)
        return _rule_content(req)


def rule_content(req: TeachingRequest) -> TeachingContent:
    """公开的规则兜底内容生成（供路由层在内容线程异常/超时时使用，避免再触发 LLM）。"""
    return _rule_content(req)


# 结构化教学内容按「概念 → 示例 → 练习」三类拆分，各自独立生成并即时下发，
# 避免一次性生成完整 JSON 时要等 20s+ 才能看到任何结构化内容（前端逐类增量补齐）。
def generate_content_parts(config: Config, req: TeachingRequest):
    """逐个产出三类结构化内容：(kind, items)。

    kind ∈ concepts | examples | exercises；每类单独一次 LLM 调用，失败回落该类规则兜底，
    任一时刻前端都能拿到「已完成的类」即时渲染，而非等全部 JSON 完成。
    """
    for kind in ("concepts", "examples", "exercises"):
        yield kind, _gen_content_kind(config, req, kind)


def _gen_content_kind(config: Config, req: TeachingRequest, kind: str) -> list:
    """生成某一类结构化内容（concepts/examples/exercises）。"""
    model = _KIND_MODEL[kind]
    if config.llm_enabled:
        try:
            data = _llm(config, 0.4)(_KIND_SYSTEM_PROMPTS[kind], human=_kind_human(req, kind))
            raw = data.get("items") or []
            out: list = []
            for it in raw[:6]:
                out.append(model(**{k: it.get(k) for k in model.model_fields if k in it}))
            if out:
                return out
        except Exception:  # noqa: BLE001 - 单类失败回落该类的规则兜底，不阻断增量推进
            logger.warning("generate_content kind=%s 失败，回退规则", kind, exc_info=True)
    return list(getattr(_rule_content(req), kind))


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
        # _LLMContent → 领域 TeachingContent（类型名不同但字段一致）
        inner = parsed.content
        content = TeachingContent(
            concepts=list(inner.concepts),
            examples=list(inner.examples),
            exercises=list(inner.exercises),
        )
        return {
            "opening": parsed.opening,
            "content": content,
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

def _rule_opening(req: TeachingRequest) -> str:
    name = req.skill_name or req.task_title
    return (
        f"我们开始学习「{name}」。\n本次目标：{req.learning_objective or req.task_title}。\n"
        f"学完后，你应该能达成：{req.acceptance_criteria or ('掌握' + name + '并能完成一次可运行验证')}。"
    )


def _rule_content(req: TeachingRequest) -> TeachingContent:
    name = req.skill_name or req.task_title
    return TeachingContent(
        concepts=[
            TeachingConcept(title="核心概念", explanation=f"围绕 {name} 的核心概念、作用与适用场景展开。"),
            TeachingConcept(title="工作原理", explanation=f"说明 {name} 在父框架上下文中的运作机制与关键要素。"),
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
    )


def _rule_start(req: TeachingRequest) -> dict:
    return {
        "opening": _rule_opening(req),
        "content": _rule_content(req),
    }


def _rule_turn(user_message: str) -> dict:
    return {
        "message": "（离线兜底）我已收到你的问题，当前无 LLM 可用。请稍后再试，或先按上面给出的概念、示例与练习自主实践。",
        "mode": "explain",
    }


# ---------------- Prompt ----------------

def _task_context(req: TeachingRequest) -> str:
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
    )


def _start_human(req: TeachingRequest) -> str:
    return (
        _task_context(req)
        # 花括号转义为 {{/}} 以规避 ChatPromptTemplate 将其解析为模板变量
        + "只输出一段合法 JSON（不要 markdown 代码块），结构如下：\n"
        '{{"opening":"1~2 句口语开场并明确本次目标",'
        '"content":{{"concepts":[{{"title":"概念名","explanation":"概念讲解"}}],'
        '"examples":[{{"title":"示例名","explanation":"讲解","code":"可选，代码"}}],'
        '"exercises":[{{"title":"练习名","instruction":"做什么","expected_result":"预期结果","hint":"可选提示"}}]}}}}'
    )


def _opening_human(req: TeachingRequest) -> str:
    return (
        f"技能：{req.skill_name}（id: {req.skill_id}）\n"
        f"任务标题（学习目标）：{req.task_title}\n"
        f"学习目标要点：{req.learning_objective}\n"
        f"验收标准：{req.acceptance_criteria}\n"
    )


def _content_human(req: TeachingRequest) -> str:
    return _task_context(req)


def _kind_human(req: TeachingRequest, kind: str) -> str:
    """仅要求模型输出某一类的一条 items 列表（单类更小更快，便于走增量下发）。JSON 花括号需转义。"""
    return (
        _task_context(req)
        + f"本阶段只生成「{kind}」这一类，不要输出其他类型。只输出一段合法 JSON（不要 markdown 代码块）：\n"
        + f"{{{{\"items\":[{_KIND_ITEM_SCHEMA[kind]}]}}}}"
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
        "只输出一段合法 JSON：{{\"message\":\"你的讲解/回答（按需引用上面的概念、示例、练习）\","
        '"mode":"explain 或 question 或 exercise 或 verify"}}。'
    )


# ---------------- Prompt 表 ----------------

# 按类生成：只要求输出某一类的 items，输出更短更快，逐个经 SSE content_part 下发
_KIND_ITEM_SCHEMA = {
    "concepts": '{{"title":"概念名","explanation":"概念讲解"}}',
    "examples": '{{"title":"示例名","explanation":"一句讲解","code":"短而完整的可运行代码(5~12行)"}}',
    "exercises": '{{"title":"练习名","instruction":"做什么","expected_result":"预期结果","hint":"可选提示"}}',
}

# 按类生成：只要求输出某一类的 items，输出更短更快，逐个经 SSE content_part 下发
_KIND_SYSTEM_PROMPTS = {
    "concepts": """你是 SkillPilot 的 TeachingAgent——耐心的技术讲师。针对下面的学习任务，只生成「核心概念」这一类。
输出 3~5 个概念，每个含 title 与 explanation，用通俗语言讲清「是什么、为什么、怎么用」。只输出一段合法 JSON：{{"items":[...]}}，不要 markdown 代码块、不要输出其他类型。不是「概念」内容的一律不要。""",
    # Examples 性能专项：把输出 token 压缩下来——每示例只讲一个知识点、代码 5~12 行、一句话讲解。
    # profiling 证实耗时 ~ 输出 token（代码 token 尤其拖慢），故硬性约束代码规模与讲解长度。
    "examples": """你是 SkillPilot 的 TeachingAgent——耐心的技术讲师。针对下面的学习任务，只生成「代码示例」这一类，共 2~3 个。硬性要求：
- 每个示例「只」演示一个核心知识点，不要混讲多个；
- 代码必须完整且可运行，但克制规模：每段 code 控制在 5~12 行以内、不超过 200 个 token；
- explanation 只用一句话讲清这段演示了什么、关键点在哪，不写背景、不串联上下文；
- 禁止重复教学内容，禁止输出与当前学习任务无关的内容；
- 不要给出完整工程、目录结构、build/运行步骤或多余注释。
每个示例只含 title / explanation / code 三个字段。只输出一段合法 JSON：{{"items":[...]}}，不要 markdown 代码块、不要输出其他类型。禁止编造不存在的 API。""",
    "exercises": """你是 SkillPilot 的 TeachingAgent——耐心的技术讲师。针对下面的学习任务，只生成「练习与验收」这一类。
输出 1~3 个贴合验收标准的练习，每个含 title、instruction、expected_result、可选 hint，引导动手验证而非空谈。只输出一段合法 JSON：{{"items":[...]}}，不要 markdown 代码块、不要输出其他类型。""",
}

_OPENING_SYSTEM_PROMPT = """你是 SkillPilot 的 TeachingAgent——一名耐心的技术讲师。用户即将开始学习一个具体任务。
请用 1~3 句口语开场，向用户点明本次学习目标与验收标准，不要加 markdown 标题、不要列表、不要代码。
直接输出开场文本即可，不要输出 JSON。"""

# 结构化内容：只产出 concepts / examples / exercises（不包含 opening），后台线程并行生成。
# 注意：system 消息也会被 ChatPromptTemplate 渲染，JSON 花括号必须转义为 {{/}}。
_CONTENT_SYSTEM_PROMPT = """你是 SkillPilot 的 TeachingAgent——一名耐心的技术讲师。针对下面这个学习任务，生成结构化教学内容。
只输出一段合法 JSON（不要 markdown 代码块），结构如下：
{{"content":{{"concepts":[{{"title":"概念名","explanation":"概念讲解"}}],
"examples":[{{"title":"示例名","explanation":"讲解","code":"可选，代码"}}],
"exercises":[{{"title":"练习名","instruction":"做什么","expected_result":"预期结果","hint":"可选提示"}}]}}}}
要求：concepts 3~6 个、examples 1~3 个、exercises 1~3 个，紧密围绕任务的学习目标与验收标准，禁止编造不存在的 API；不确定的用法用「...」占位并说明。"""

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