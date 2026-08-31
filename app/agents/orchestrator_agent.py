"""Orchestrator Agent —— 对话入口：识别意图 → 结构化回复（引导到已上线的业务能力）。

- LLM 可用（配置了 LLM_API_KEY）时使用 LLM + Structured Output；
- LLM 不可用 / 调用失败时回退到规则实现，保证管道始终返回标准 JSON；
- 上下文恢复：通过 State 中的 messages（Checkpointer 持久化）实现；
- 顶层意图：chat / tech_learning / job_search / plan_generation（对齐架构方案第 4 节）。
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field

from app.agents.base import BaseAgent
from app.config import Config
from app.contracts import VALID_INTENTS
from app.orchestrator.state import SkillMapState

logger = logging.getLogger(__name__)

# 规则意图识别的关键词（规则兜底，LLM 不可用时使用）。
# 顺序有语义：job_search / plan_generation 的关键词比 tech_learning 更具体，
# 需先匹配（如「学习计划」先于「学习」命中，避免误判）。
_INTENT_KEYWORDS: dict[str, tuple[str, ...]] = {
    "job_search": (
        "找工作", "求职", "应聘", "面试", "招聘", "想找", "找份", "岗位", "跳槽", "offer",
    ),
    "plan_generation": (
        "学习计划", "学习路线", "学习路径", "规划", "路线", "计划表", "多久能",
    ),
    "tech_learning": (
        "我想学", "我要学", "想学", "自学", "学一下", "学一学", "学习", "掌握", "入门", "精通", "提升",
        "想系统学习", "想学习", "要学习", "准备学", "准备学习", "打算学", "想掌握", "学会",
        "怎么学", "如何学", "怎么入门", "怎么系统学", "从零学",
    ),
}

# 非 chat 的业务意图（多轮追问续接用）
_BUSINESS_INTENTS = {i for i in VALID_INTENTS if i != "chat"}

# 消息里明确点名「想学的技能」的常见句式（用于技能解析失败时做目标指纹兜底）
_NEW_SKILL_RE = re.compile(
    r"(?:想学|要学|学一下|自学|学会|学习|掌握|入门)\s*(?:一门|一个|一下)?\s*([^\s，。,;；!！?？]+)",
    re.UNICODE,
)


def _turn_goal_fingerprint(intent: str, params: dict) -> str:
    """本轮消息明确点名的业务目标指纹；没有具体目标返回空串。

    用于区分「切到新目标」（Go→PHP）与「细看/续接现有计划」（学习计划详细说说）：
    后者没有点名任何技能/岗位 → 指纹为空 → 不触发新任务重置。
    """
    if intent == "tech_learning":
        skills = params.get("target_skills") or []
        if skills:
            ids = sorted(s.get("skill_id") or s.get("skill_name") for s in skills)
            return "skill:" + ",".join(ids)
        # 技能未命中语料库（如 PHP），但消息明显在说想学某技术 → 用词面兜底指纹
        raw = (params.get("_raw_message") or "").strip()
        m = _NEW_SKILL_RE.search(raw)
        if m:
            return "skillraw:" + m.group(1).strip().lower()
        return ""
    if intent in ("plan_generation", "job_search"):
        roles = params.get("target_roles") or []
        if roles:
            return "role:" + ",".join(sorted(roles))
        if params.get("skill_id"):
            return "skill:" + params["skill_id"]
        return ""
    return ""


def _active_goal_fingerprint(state: dict) -> str:
    """上一轮任务在 State 中已确立的目标指纹（当前正在进行的业务目标）。"""
    tp = state.get("target_profile") or {}
    skills = tp.get("skills") or []
    if skills:
        return "skill:" + ",".join(sorted(str(s.get("skill_id") or "") for s in skills))
    if state.get("user_goal"):
        return "goalname:" + str(state.get("user_goal") or "")
    return ""


class AgentOutput(BaseModel):
    """Agent 结构化输出契约（Pydantic / Structured Output）。"""

    intent: str = Field(description="识别出的意图")
    reply: str = Field(description="给用户的回复文本")
    confidence: float = Field(ge=0.0, le=1.0, description="置信度 0-1")
    workflow_status: str = Field(default="done")
    artifacts: dict[str, Any] = Field(default_factory=dict)
    # LLM 负责「理解用户想学什么」：把明确点名的目标技能名填进 target_skills，
    # 具体规范化（技能库是否存在）交给 Skill Resolver / intent_parser 处理。
    target_skills: list[str] = Field(
        default_factory=list,
        description="用户想学的技能名列表（tech_learning）；只填名称，规范性由下游解析",
    )
    target_roles: list[str] = Field(
        default_factory=list,
        description="目标岗位名或 role_id（job_search / plan_generation）",
    )


def _shorten(text: str, limit: int = 24) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


class OrchestratorAgent(BaseAgent):
    name = "orchestrator_agent"

    def __init__(self, config: Config) -> None:
        self.config = config
        self._llm: Any = None  # None=未初始化；False=不可用

    # ---------------- LLM 路径（可选） ----------------

    def _get_llm(self):
        if not self.config.llm_enabled:
            return None
        if self._llm is None:
            try:
                from langchain_openai import ChatOpenAI

                self._llm = ChatOpenAI(
                    model=self.config.llm_model,
                    base_url=self.config.llm_base_url,
                    api_key=self.config.llm_api_key,
                    temperature=0,
                )
            except Exception:  # noqa: BLE001
                logger.warning("langchain_openai 不可用，回退规则实现", exc_info=True)
                self._llm = False
        return self._llm if self._llm else None

    def _run_with_llm(
        self, message: str, intent_hint: str | None, history: list[dict]
    ) -> dict[str, Any] | None:
        """调用 LLM 结构化输出；失败返回 None 交由规则兜底。"""
        llm = self._get_llm()
        if not llm:
            return None
        try:
            from langchain_core.prompts import ChatPromptTemplate

            history_text = "\n".join(
                f"{m['role']}: {m['content']}" for m in history[-6:]
            )
            prompt = ChatPromptTemplate.from_messages(
                [
                    (
                        "system",
                        "你是 SkillMap 的意图识别与回复助手。只能从给定枚举中选择意图，"
                        "结合历史对话给出简洁、可执行的回复。只输出符合 schema 的 JSON。\n"
                        "若意图为 tech_learning，请把用户想学的技能名写入 target_skills 列表"
                        "（如 [\"PHP\"]）。target_roles 用于 job_search / plan_generation 的目标岗位。",
                    ),
                    (
                        "human",
                        "可选意图: {intents}\nintent_hint: {hint}\n历史对话:\n{history}\n"
                        "当前消息: {msg}",
                    ),
                ]
            )
            chain = prompt | llm.with_structured_output(AgentOutput)
            result = chain.invoke(
                {
                    "intents": "、".join(sorted(VALID_INTENTS)),
                    "hint": intent_hint or "null",
                    "history": history_text or "（无）",
                    "msg": message,
                }
            )
            if isinstance(result, AgentOutput):
                return result.model_dump()
            if isinstance(result, dict):
                return AgentOutput.model_validate(result).model_dump()
            return None
        except Exception:  # noqa: BLE001
            logger.warning("LLM 调用失败，回退规则实现", exc_info=True)
            return None

    # ---------------- 聊天回复：正常大语言模型对话（LLM 可用时） ----------------

    def _get_chat_llm(self):
        """用于自然对话的 LLM（温度较高，非结构化）。"""
        if not self.config.llm_enabled:
            return None
        try:
            from langchain_openai import ChatOpenAI

            return ChatOpenAI(
                model=self.config.llm_model,
                base_url=self.config.llm_base_url,
                api_key=self.config.llm_api_key,
                temperature=0.7,
            )
        except Exception:  # noqa: BLE001
            logger.warning("langchain_openai 不可用，聊天回退规则实现", exc_info=True)
            return None

    def _chat_reply_llm(self, message: str, history: list[dict]) -> str | None:
        """用 LLM 生成自然对话回复；需要检索时注入网络参考；失败返回 None。"""
        llm = self._get_chat_llm()
        if not llm:
            return None
        try:
            from langchain_core.prompts import ChatPromptTemplate

            from app.agents.websearch import web_context

            history_text = "\n".join(
                f"{m['role']}: {m['content']}" for m in history[-10:]
            )
            ctx = web_context(message)
            system = (
                "你是 SkillMap 的学习与职业成长助手。请像普通的大语言模型一样自然、"
                "友好、简洁地回答用户问题：先直接给出答案，需要时可以补充举例；"
                "对话中保持与历史记录一致。"
            )
            if ctx:
                system += (
                    "\n\n用户的问题适合联网检索，以下是联网获取到的参考资料（[n] 为来源编号）。"
                    "请结合这些资料作答：在关键结论后标注对应来源编号，如【来源[1]】；"
                    "若资料与本问题无关或不足以回答，请如实说明。\n"
                    "参考资料：\n" + ctx
                )
            prompt = ChatPromptTemplate.from_messages(
                [
                    ("system", system),
                    ("human", "历史对话：\n{history}\n\n当前用户：{msg}"),
                ]
            )
            resp = (prompt | llm).invoke({"history": history_text or "（无）", "msg": message})
            content = (resp.content or "").strip()
            return content or None
        except Exception:  # noqa: BLE001
            logger.warning("LLM 自然对话失败，回退规则实现", exc_info=True)
            return None

    # ---------------- 规则兜底路径 ----------------

    def _classify_intent_rules(self, message: str, intent_hint: str | None) -> tuple[str, float]:
        if intent_hint in VALID_INTENTS:
            return intent_hint, 0.9
        for intent, keywords in _INTENT_KEYWORDS.items():
            if any(k in message for k in keywords):
                return intent, 0.8
        return "chat", 0.6

    @staticmethod
    def _reset_business_state() -> dict[str, Any]:
        """开启全新目标（Go → PHP）时，清理上一任务遗留的业务状态。

        区分「会话状态」（messages 长期保留）与「当前任务状态」：当前任务切换到新目标后，
        旧的目标画像 / 访谈 / 计划 / artifacts 必须失效，否则会被路由或 reply_node 复用，
        导致「换了学习目标却仍输出旧计划」。
        """
        return {
            "is_new_task": True,
            "user_goal": None,
            "target_role": None,
            "target_profile": None,
            "user_profile": None,
            "skill_gaps": [],
            "skill_profile": {},
            "skill_gap": {},
            "learning_plan": {},
            "practice_plan": {},
            "evaluation_report": {},
            "interview_state": {},
            "retrieved_evidence": [],
            "artifacts": {},
            "summary": "",
            "error": None,
            "steps": ["intent_recognize"],
        }

    def _fallback(
        self, message: str, intent_hint: str | None, history: list[dict], turn: int
    ) -> dict[str, Any]:
        """chat 意图的 LLM 不可用时的兜底回复（自然但不机械）。"""
        intent, confidence = self._classify_intent_rules(message, intent_hint)
        first_user = next((m["content"] for m in history if m["role"] == "user"), None)
        if first_user and first_user.strip() != message:
            reply = (
                f"结合你之前说的「{_shorten(first_user)}」，我们来继续这个话题。"
                "你想聊技术、答疑，还是生成一份学习计划？"
            )
        elif any(k in message for k in ("你好", "嗨", "hi", "hello", "在吗")):
            reply = "你好呀，我是 SkillMap 学习助手。想聊技术、问问题，或生成一份学习计划都可以。"
        else:
            reply = (
                "我收到你的消息了。目前我还没接上大模型，先用规则兜底回应："
                "你可以继续聊聊想学的技术、提问任何知识问题，"
                "或告诉我目标岗位（如「帮我生成 Python 后端工程师的学习计划」）来规划学习路线。"
            )
        return {
            "intent": intent,
            "reply": reply,
            "confidence": confidence,
            "workflow_status": "done",
            "artifacts": {},
        }

    # ---------------- 主入口 ----------------

    def invoke(self, state: SkillMapState) -> dict[str, Any]:
        message = (state.get("message") or "").strip()
        intent_hint = state.get("intent_hint")
        history = state.get("messages") or []  # Checkpointer 恢复的历史
        turn = len(history) // 2 + 1

        # 意图识别：LLM 增强优先，失败走规则（确定性可重复）
        output = self._run_with_llm(message, intent_hint, history) or {}
        intent = output.get("intent") or self._classify_intent_rules(message, intent_hint)[0]

        # 强制采纳上层已确定性推断的业务意图：streamer 层已按关键词把「我想学 java」判为
        # tech_learning 并作为 intent_hint 传入，LLM 仅把 hint 当提示词、仍可能误判回 chat，
        # 导致 learning_plan 不生成、前端无可实时可视化。业务意图必须被可靠执行。
        if intent_hint in _BUSINESS_INTENTS:
            intent = intent_hint

        # 意图校正：plan_generation 需要显式「计划/路线」类措辞；仅「想学某技能」
        # 应走 tech_learning 完整闭环（目标画像 → 访谈 → 缺口），避免 LLM 混淆两者。
        if intent == "plan_generation" and intent_hint not in VALID_INTENTS:
            if not any(k in message for k in _INTENT_KEYWORDS["plan_generation"]) and any(
                k in message for k in _INTENT_KEYWORDS["tech_learning"]
            ):
                intent = "tech_learning"

        # 多轮追问续接：上一轮 need_input（已给出业务意图但缺入参），本轮又无任何
        # 业务关键词（视为用户在回答追问，如补说岗位名）→ 续接上一轮意图，仅用新消息重解析入参。
        prev_status = state.get("workflow_status")
        prev_intent = state.get("intent")
        promoted_from_answer = False
        if (
            intent == "chat"
            and prev_status == "need_input"
            and prev_intent in _BUSINESS_INTENTS
        ):
            intent = prev_intent
            promoted_from_answer = True

        # 阶段 9：意图 → 结构化入参（目标岗位/代码块等），供路由节点消费。
        # LLM 负责「理解用户想学什么」（output.target_skills），Skill Resolver 负责规范化。
        from app.agents import intent_parser

        params = intent_parser.parse(
            self.config, message, intent, llm_targets=output.get("target_skills")
        )
        params["_raw_message"] = message  # 供目标指纹在技能未命中时做词面兜底

        # chat 意图由本 Agent 直接回复（LLM 自然对话优先，规则兜底）；业务意图交给路由节点
        summary = ""
        if intent == "chat":
            summary = (
                self._chat_reply_llm(message, history)
                or output.get("reply")
                or self._fallback(message, intent_hint, history, turn)["reply"]
            )

        # —— 新任务检测：本轮明确点名了「不同于当前任务」的新目标（不是回答追问、不是细看旧计划）——
        trigger_turn = intent in _BUSINESS_INTENTS and not promoted_from_answer
        if trigger_turn:
            turn_g = _turn_goal_fingerprint(intent, params)
            active_g = _active_goal_fingerprint(state)
            has_prev_task = (
                bool(active_g)
                or prev_intent in _BUSINESS_INTENTS
                or state.get("target_profile") is not None
                or (state.get("interview_state") or {}).get("active")
            )
            # 本轮点名了新目标、且确实与当前任务目标不同 → 切到新任务（进行一次状态清理）
            is_new_task = bool(turn_g) and has_prev_task and turn_g != active_g
        else:
            is_new_task = False

        result = {
            "intent": intent,
            "intent_params": params,
            "summary": summary,
            "current_agent": self.name,
            "workflow_status": "pending",
            "error": None,
            "steps": ["intent_recognize"],
            "is_new_task": is_new_task,
        }
        # 开启新任务：合并旧业务状态清理，确保本轮从干净的当前任务状态开始
        if is_new_task:
            result.update(self._reset_business_state())
            result["is_new_task"] = True
            result["intent"] = intent
            result["intent_params"] = params
            result["current_agent"] = self.name
            result["workflow_status"] = "pending"
        return result
