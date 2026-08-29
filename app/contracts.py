"""全局契约常量（供 API 层与 Agent 层共享，避免跨层耦合）。

顶层意图（对齐架构方案第 4 节）：
- chat：普通对话
- tech_learning：技术学习（用户要学某技术 → 目标技能画像 → 访谈 → 缺口 → 学习计划）
- job_search：岗位求职（用户要找某岗位 → 目标技能画像 → 访谈 → 缺口 → 岗位匹配）
- plan_generation：学习计划快捷路径（显式「生成学习计划/路线」，直接产出计划）
"""
from __future__ import annotations

from typing import Literal, get_args

INTENT_HINTS = Literal[
    "tech_learning",
    "job_search",
    "plan_generation",
    "chat",
]

VALID_INTENTS: frozenset[str] = frozenset(get_args(INTENT_HINTS))
