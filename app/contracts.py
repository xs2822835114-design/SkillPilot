"""全局契约常量（供 API 层与 Agent 层共享，避免跨层耦合）。

精简后仅保留两条主线：普通对话 chat 与学习计划 plan_generation。
其余意图（画像/缺口/评估/访谈/RAG 等）已按需求移除。
"""
from __future__ import annotations

from typing import Literal, get_args

INTENT_HINTS = Literal[
    "plan_generation",
    "chat",
]

VALID_INTENTS: frozenset[str] = frozenset(get_args(INTENT_HINTS))
