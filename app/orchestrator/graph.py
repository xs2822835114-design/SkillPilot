"""LangGraph 编排图：构建、编译、绑定 Checkpointer。"""
from __future__ import annotations

from typing import Any

from langgraph.graph import END, START, StateGraph

from app.agents.orchestrator_agent import OrchestratorAgent
from app.config import Config
from app.orchestrator.state import SkillMapState


def build_graph(config: Config, checkpointer: Any = None):
    """构建并编译阶段 1 最小图：START -> orchestrator_agent -> END。"""
    orchestrator = OrchestratorAgent(config)

    builder = StateGraph(SkillMapState)
    builder.add_node("orchestrator_agent", orchestrator.invoke)
    builder.add_edge(START, "orchestrator_agent")
    builder.add_edge("orchestrator_agent", END)

    return builder.compile(checkpointer=checkpointer)
