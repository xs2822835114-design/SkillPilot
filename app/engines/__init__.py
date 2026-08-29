"""Engine 层（方案第 15、16 节）：确定性、可复现、可单测的计算逻辑。

与 Agent 的职责边界：
- Agent 负责自然语言理解 / 对话 / 追问 / 决策；
- Engine 负责技能等级估算、技能图谱遍历、缺口计算、岗位匹配、学习路径排序。

本层只依赖 domain 契约与 knowledge 层，不依赖 Agent / HTTP / LLM，保证：
- 结果可重复；
- 换模型/改对话逻辑不影响计算；
- 可逐函数做单元测试。
"""
from __future__ import annotations

from app.engines.skill_engine import estimate_level
from app.engines.gap_engine import compute_gaps
from app.engines.recommendation_engine import (
    build_learning_path,
    build_learning_plan,
    recommend_roles,
)

__all__ = [
    "estimate_level",
    "compute_gaps",
    "build_learning_path",
    "build_learning_plan",
    "recommend_roles",
]