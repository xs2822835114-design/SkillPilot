"""Orchestrator Agent —— 对话入口：识别意图 → 结构化回复（引导到已上线的业务能力）。

- LLM 可用（配置了 LLM_API_KEY）时使用 LLM + Structured Output；
- LLM 不可用 / 调用失败时回退到规则实现，保证管道始终返回标准 JSON；
- 上下文恢复：通过 State 中的 messages（Checkpointer 持久化）实现；
- 顶层意图：chat / tech_learning / job_search / plan_generation（对齐架构方案第 4 节）。
"""
from __future__ import annotations

import logging
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
        "我想学", "我要学", "想学", "自学", "学一下", "学习", "掌握", "入门", "精通", "提升",
    ),
}

# 非 chat 的业务意图（多轮追问续接用）
_BUSINESS_INTENTS = {i for i in VALID_INTENTS if i != "chat"}


class AgentOutput(BaseModel):
    """Agent 结构化输出契约（Pydantic / Structured Output）。"""

    intent: str = Field(description="识别出的意图")
    reply: str = Field(description="给用户的回复文本")
    confidence: float = Field(ge=0.0, le=1.0, description="置信度 0-1")
    workflow_status: str = Field(default="done")
    artifacts: dict[str, Any] = Field(default_factory=dict)


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
                        "结合历史对话给出简洁、可执行的回复。只输出符合 schema 的 JSON。",
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
        if (
            intent == "chat"
            and prev_status == "need_input"
            and prev_intent in _BUSINESS_INTENTS
        ):
            intent = prev_intent

        # 阶段 9：意图 → 结构化入参（目标岗位/代码块等），供路由节点消费
        from app.agents import intent_parser

        params = intent_parser.parse(self.config, message, intent)

        # chat 意图由本 Agent 直接回复（LLM 自然对话优先，规则兜底）；业务意图交给路由节点
        summary = ""
        if intent == "chat":
            summary = (
                self._chat_reply_llm(message, history)
                or output.get("reply")
                or self._fallback(message, intent_hint, history, turn)["reply"]
            )

        return {
            "intent": intent,
            "intent_params": params,
            "summary": summary,
            "current_agent": self.name,
            "workflow_status": "pending",
            "error": None,
            "steps": ["intent_recognize"],
        }
