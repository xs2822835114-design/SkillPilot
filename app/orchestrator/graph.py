"""LangGraph 编排图：多 Agent 条件路由（精简）。

图结构：
  START → orchestrator_agent（意图识别 + 结构化入参解析）
       └─ 按 intent 条件路由：
            chat            → reply_node（直接使用 orchestrator 已产出的 summary）
            plan_generation → plan_node → reply_node
  reply_node（拼装最终回复 + 透传 artifacts）→ END

说明：
- 业务节点为纯函数（app/agents/routing），任何异常不外抛，降级由 reply_node 呈现；
- 缺入参时业务节点返回 need_input，reply_node 追问可选值；
- 已绑定 Checkpointer，保证 messages 跨轮持久化。
"""
from __future__ import annotations

from typing import Any

from langgraph.graph import END, START, StateGraph

from app.agents import routing
from app.agents.orchestrator_agent import OrchestratorAgent
from app.agents.reply import reply_node
from app.config import Config
from app.orchestrator.state import SkillMapState

# 业务节点名（供条件路由映射复用）
_BUSINESS_NODES = ("plan_node",)

_INTENT_TO_NODE = {
    "plan_generation": "plan_node",
}


def _route_intent(state: dict) -> str:
    """按 intent 将对话分发到对应业务节点；chat 或未知意图直接进 reply_node。"""
    intent = state.get("intent") or "chat"
    return _INTENT_TO_NODE.get(intent, "reply_node")


def build_graph(config: Config, checkpointer: Any = None):
    """构建并编译多 Agent 条件路由图。"""
    orchestrator = OrchestratorAgent(config)

    builder = StateGraph(SkillMapState)
    builder.add_node("orchestrator_agent", orchestrator.invoke)
    builder.add_node("plan_node", routing.make_plan_node(config))
    builder.add_node("reply_node", reply_node)

    builder.add_edge(START, "orchestrator_agent")
    builder.add_conditional_edges(
        "orchestrator_agent",
        _route_intent,
        {n: n for n in (*_BUSINESS_NODES, "reply_node")},
    )
    for node in _BUSINESS_NODES:
        builder.add_edge(node, "reply_node")
    builder.add_edge("reply_node", END)

    return builder.compile(checkpointer=checkpointer)
