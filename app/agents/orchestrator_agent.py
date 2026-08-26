"""Orchestrator Agent —— 阶段 1 最小闭环：识别意图 → 结构化回复。

- LLM 可用（配置了 LLM_API_KEY）时使用 LLM + Structured Output；
- LLM 不可用 / 调用失败时回退到规则实现，保证管道始终返回标准 JSON；
- 上下文恢复：通过 State 中的 messages（Checkpointer 持久化）实现。
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

# 规则意图识别的关键词（阶段 1 占位，后续由业务 Agent 接管）
_INTENT_KEYWORDS: dict[str, tuple[str, ...]] = {
    "profile_update": ("我会", "我的技术栈", "我做过", "掌握", "熟悉", "了解", "会 java", "会python"),
    "gap_analysis": ("缺口", "差距", "缺什么", "转型", "转行", "目标岗位", "需要学什么", "怎么入门"),
    "plan_generation": ("学习计划", "学习路线", "规划", "路线", "多久能"),
    "practice": ("实践", "练手", "项目任务", "动手"),
    "evaluation": ("评估", "评价我的", "帮我看看代码", "评分"),
    "question": ("什么是", "是什么", "区别", "怎么用", "教程", "原理"),
}


class AgentOutput(BaseModel):
    """Agent 结构化输出契约（Pydantic / Structured Output）。"""

    intent: str = Field(description="识别出的意图")
    reply: str = Field(description="给用户的回复文本")
    confidence: float = Field(ge=0.0, le=1.0, description="置信度 0-1")
    workflow_status: str = Field(default="done")
    artifacts: dict[str, Any] = Field(default_factory=dict)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


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
        intent, confidence = self._classify_intent_rules(message, intent_hint)
        first_user = next((m["content"] for m in history if m["role"] == "user"), None)
        context_note = (
            f"我记得你之前提到过：「{_shorten(first_user)}」"
            if first_user
            else "这是我们本会话的第一条消息"
        )
        if intent == "chat":
            reply = (
                f"收到你的消息（第 {turn} 轮对话）。{context_note}。"
                "当前处于阶段 1（Agent 最小闭环），业务 Agent 将在后续阶段接入。"
            )
        else:
            reply = (
                f"我识别到你希望进行「{intent}」相关分析（第 {turn} 轮对话）。{context_note}。"
                "该能力将在后续阶段（阶段 3~6）接入，当前先走通用问答。"
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

        output = self._run_with_llm(message, intent_hint, history) or self._fallback(
            message, intent_hint, history, turn
        )

        user_msg = {
            "role": "user",
            "content": message,
            "intent_hint": intent_hint,
            "created_at": _now_iso(),
        }
        assistant_msg = {
            "role": "assistant",
            "content": output["reply"],
            "intent": output["intent"],
            "created_at": _now_iso(),
        }

        return {
            "messages": list(history) + [user_msg, assistant_msg],
            "intent": output["intent"],
            "current_agent": self.name,
            "workflow_status": output.get("workflow_status", "done"),
            "error": None,
        }
