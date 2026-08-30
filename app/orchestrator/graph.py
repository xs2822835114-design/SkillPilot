"""LangGraph 编排图：多 Agent 条件路由（对齐架构方案第 3、17 节）。

图结构：
  START → orchestrator_agent（意图识别 + 结构化入参解析）
       └─ 按 intent 条件路由：
            chat            → reply_node（直接使用 orchestrator 已产出的 summary）
            plan_generation → plan_node → reply_node
            tech_learning   → tech_requirement_node ─┐
            job_search      → job_requirement_node  ─┤（目标画像）
                              ├─ learning_plan_mode="direct"（默认）
                              │    → learning_plan_node（LLM 直出结构化学习计划，跳过访谈）
                              │        → reply_node → END
                              └─ learning_plan_mode="interview"（精准模式，保留）
                                   → interview_node（跨轮访谈，产出 user_profile）
                                       ├─ 还需更多信息 → reply_node（need_input 追问）
                                       └─ 访谈完成      → gap_node（缺口 + 学习路径/岗位匹配）
                                                             → reply_node → END

说明：
- 业务节点为纯函数（app/agents/routing | interview | learning_plan_agent），任何异常不外抛，降级由 reply_node 呈现；
- 缺入参时业务节点返回 need_input，reply_node 追问可选值；
- 访谈状态（interview_state / user_profile / target_profile）靠 Checkpointer 跨轮持久化；
- 已绑定 Checkpointer，保证 messages 跨轮持久化。
"""
from __future__ import annotations

from typing import Any

from langgraph.graph import END, START, StateGraph

from app.agents import routing
from app.agents.interview import make_interview_node
from app.agents.learning_plan_agent import make_learning_plan_node
from app.agents.orchestrator_agent import OrchestratorAgent
from app.agents.reply import reply_node
from app.config import Config
from app.orchestrator.state import SkillMapState

# 业务节点名（供条件路由映射复用）
_BUSINESS_NODES = ("plan_node", "tech_requirement_node", "job_requirement_node")

_INTENT_TO_NODE = {
    "plan_generation": "plan_node",
    "tech_learning": "tech_requirement_node",
    "job_search": "job_requirement_node",
}


def _route_intent(state: dict) -> str:
    """按 intent 将对话分发到对应业务节点；chat 或未知意图直接进 reply_node。

    - 本轮开启了全新的业务目标（Go → PHP，``is_new_task``）：**必须**按当前新意图路由，
      否则旧访谈 / 旧状态会拦截切换，导致继续走上一目标的流程。
    - 仅在没有新任务、访谈进行中（interview_state.active）时，才优先续接访谈，
      避免用户回答被重新意图分类而中断访谈。
    """
    if state.get("is_new_task"):
        intent = state.get("intent") or "chat"
        return _INTENT_TO_NODE.get(intent, "reply_node")
    if (state.get("interview_state") or {}).get("active"):
        return "interview_node"
    intent = state.get("intent") or "chat"
    return _INTENT_TO_NODE.get(intent, "reply_node")


def _after_requirement(config: Config, state: dict) -> str:
    """技术/岗位需求节点后：成功建立目标画像 → 默认直接生成学习计划；
    当 learning_plan_mode="interview"（精准模式）则进入技能访谈。"""
    if state.get("target_profile") and state.get("workflow_status") == "done":
        if getattr(config, "learning_plan_mode", "direct") == "direct":
            return "learning_plan_node"
        return "interview_node"
    return "reply_node"


def _after_interview(state: dict) -> str:
    """访谈节点后：访谈完成 → 缺口引擎；仍需追问 → reply。"""
    if state.get("workflow_status") == "done":
        return "gap_node"
    return "reply_node"


def build_graph(config: Config, checkpointer: Any = None):
    """构建并编译多 Agent 条件路由图。"""
    orchestrator = OrchestratorAgent(config)

    builder = StateGraph(SkillMapState)
    builder.add_node("orchestrator_agent", orchestrator.invoke)
    builder.add_node("plan_node", routing.make_plan_node(config))
    builder.add_node("tech_requirement_node", routing.make_tech_requirement_node(config))
    builder.add_node("job_requirement_node", routing.make_job_requirement_node(config))
    builder.add_node("interview_node", make_interview_node(config))
    builder.add_node("gap_node", routing.make_gap_node(config))
    builder.add_node("learning_plan_node", make_learning_plan_node(config))
    builder.add_node("reply_node", reply_node)

    builder.add_edge(START, "orchestrator_agent")
    builder.add_conditional_edges(
        "orchestrator_agent",
        _route_intent,
        {
            "plan_node": "plan_node",
            "tech_requirement_node": "tech_requirement_node",
            "job_requirement_node": "job_requirement_node",
            "interview_node": "interview_node",
            "reply_node": "reply_node",
        },
    )
    builder.add_edge("plan_node", "reply_node")
    builder.add_conditional_edges(
        "tech_requirement_node",
        lambda s: _after_requirement(config, s),
        {
            "learning_plan_node": "learning_plan_node",
            "interview_node": "interview_node",
            "reply_node": "reply_node",
        },
    )
    builder.add_conditional_edges(
        "job_requirement_node",
        lambda s: _after_requirement(config, s),
        {
            "learning_plan_node": "learning_plan_node",
            "interview_node": "interview_node",
            "reply_node": "reply_node",
        },
    )
    builder.add_edge("learning_plan_node", "reply_node")
    builder.add_conditional_edges(
        "interview_node",
        _after_interview,
        {"gap_node": "gap_node", "reply_node": "reply_node"},
    )
    builder.add_edge("gap_node", "reply_node")
    builder.add_edge("reply_node", END)

    return builder.compile(checkpointer=checkpointer)
