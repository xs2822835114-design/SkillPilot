"""Engine 层（方案第 15、16 节）：确定性、可复现、可单测的计算逻辑。

与 Agent 的职责边界：
- Agent 负责自然语言理解 / 对话 / 追问 / 决策；
- Engine 负责技能图谱遍历、学习路径排序（预留下线模块的技能估算/缺口计算/岗位匹配已随访谈、缺口分析一并移除）。

本层只依赖 domain 契约与 knowledge 层，不依赖 Agent / HTTP / LLM，保证：
- 结果可重复；
- 换模型/改对话逻辑不影响计算；
- 可逐函数做单元测试。
"""
from __future__ import annotations

from app.engines.recommendation_engine import (
    build_learning_path,
)

__all__ = [
    "build_learning_path",
]