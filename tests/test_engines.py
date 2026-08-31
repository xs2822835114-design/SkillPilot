"""Engine 层单元测试：学习路径排序（recommendation_engine）。

技能等级估算 / 缺口引擎在访谈、缺口分析下线后已随相关模块一并移除，
此处仅保留仍被学习计划生成复用的学习路径排序。
全部基于内存知识库（无 DB / 无 LLM），确定性、可在 CI 始终运行。
"""
from __future__ import annotations

from app.config import Config


def test_build_learning_path_topological():
    from app.engines import build_learning_path

    cfg = Config(env="test", database_url="", llm_api_key="", checkpointer_backend="memory")
    path = build_learning_path(cfg, ["langgraph", "python", "langchain", "llm_api"])
    # 前置者先：python/llm_api 先于 langchain，langchain 先于 langgraph
    assert path.index("python") < path.index("langgraph")
    assert path.index("llm_api") < path.index("langchain")
    assert path.index("langchain") < path.index("langgraph")