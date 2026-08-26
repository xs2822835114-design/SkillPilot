"""全局契约常量（供 API 层与 Agent 层共享，避免跨层耦合）。"""
from __future__ import annotations

from typing import Literal, get_args

INTENT_HINTS = Literal[
    "profile_update",
    "gap_analysis",
    "plan_generation",
    "practice",
    "evaluation",
    "question",
    "chat",
]

VALID_INTENTS: frozenset[str] = frozenset(get_args(INTENT_HINTS))
