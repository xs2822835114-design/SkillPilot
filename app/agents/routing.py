"""多 Agent 路由节点：按意图调用业务 service，产出 State 快照与摘要。

节点（对齐架构方案第 3、16 节）：
- plan_node：学习计划快捷路径（显式「生成学习计划/路线」）；
- tech_requirement_node：技术学习目标 → TargetProfile；
- job_requirement_node：岗位求职目标 → TargetProfile。

约定：
- 节点是**纯函数**（读 State → 调 service → 合并回 State），不感知 HTTP；
- 任何异常都不外抛：写 `state["error"]` 并降级，交由 reply_node 产出友好回复；
- 缺必填入参 → `workflow_status="need_input"`，reply_node 追问可选值；
- 目标画像统一落到 `target_profile`（TargetProfile 契约），供学习计划生成复用。
"""
from __future__ import annotations

import logging
from typing import Any, Callable

from app.config import Config
from app.agents import intent_parser

logger = logging.getLogger(__name__)


def _need_input(agent: str, message: str) -> dict[str, Any]:
    return {
        "workflow_status": "need_input",
        "current_agent": agent,
        "error": {"type": "need_input", "message": message},
        "summary": "",
    }


def _degraded(agent: str, message: str) -> dict[str, Any]:
    return {
        "workflow_status": "degraded",
        "current_agent": agent,
        "error": {"type": "service_error", "message": message},
        "summary": "",
    }


def _done(summary: str, artifacts: dict, agent: str, **snapshots: dict) -> dict[str, Any]:
    out: dict[str, Any] = {
        "workflow_status": "done",
        "error": None,
        "summary": summary,
        "artifacts": artifacts,
        "current_agent": agent,
    }
    out.update({k: v for k, v in snapshots.items() if v is not None})
    return out


# ---------------- plan ----------------

def _plan_detail_reply(existing: list) -> dict[str, Any]:
    """已有学习计划（本 thread 由学习计划生成器产生的 learning_plan）时，用户说「计划详细说说」等
    不是要新建计划，而是想细看既有计划：直接给出环节明细并引导到技能图谱/学习计划页。

    existing 结构见学习计划生成器产出的 learning_plan，含 skill_name / level / steps。
    """
    lines = [
        f"你已有 {len(existing)} 项技能学习安排。按学习顺序，每个技能的环节如下（完整大纲可到「技能图谱」/「学习计划」页查看）："
    ]
    for i, it in enumerate(existing, 1):
        name = it.get("skill_name") or it.get("skill_id") or "技能"
        head = f"{i}. {name}"
        if it.get("level"):
            head += f"（{it['level']}）"
        lines.append(head)
        for s in (it.get("steps") or []):
            lines.append(f"   · {s}")
    return _done(
        "\n".join(lines),
        {
            "intent": "plan_generation",
            "learning_plan": existing,
            "goto": {"page": "graph"},
        },
        "plan_agent",
    )


def _resolve_role_for_skill(config: Config, skill_id: str) -> dict | None:
    """技能 → 目标岗位：找到把该技能列为要求（权重最高优先）的岗位。

    供「我想学 Flask」这类按技能生成计划的场景：把技能反查成目标岗位后走既有
    role-based 规划链路。读取失败返回 None（由调用方追问）。
    """
    try:
        from app.gap import graph_store

        best: dict | None = None
        best_weight = -1.0
        for role in graph_store.list_roles(config):
            loaded = graph_store.load_role(config, role["role_id"])
            if not loaded:
                continue
            for req in loaded.requirements:
                if req.skill_id == skill_id and req.weight > best_weight:
                    best = {"role_id": loaded.role_id, "role_name": loaded.role_name}
                    best_weight = req.weight
        return best
    except Exception:  # noqa: BLE001
        logger.warning("技能→岗位反查失败 skill=%s", skill_id, exc_info=True)
        return None


def make_plan_node(config: Config) -> Callable[[dict], dict]:
    def node(state: dict) -> dict:
        params = state.get("intent_params") or {}
        roles = params.get("target_roles") or []
        skill_id = params.get("skill_id")
        role_from_skill = None
        if not roles:
            if skill_id and config.database_url:
                role_from_skill = _resolve_role_for_skill(config, skill_id)
                if role_from_skill:
                    roles = [role_from_skill["role_id"]]
            if not roles:
                # 用户可能只是想细看本 thread 已生成的计划（如「学习计划详细说说」），
                # 而非新建计划 → 直接给出既有计划明细，避免误以为要重新选择目标。
                existing = (state.get("artifacts") or {}).get("learning_plan") or []
                if existing:
                    return _plan_detail_reply(existing)
                return _need_input(
                    "plan_agent",
                    f"你想学哪个技能或为哪个目标岗位生成学习计划？可选岗位：{intent_parser.list_role_names(config)}"
                    f"；或直接说想学的技能，如 {intent_parser.list_skill_names(config, 3)}",
                )
        if not config.database_url:
            return _degraded("plan_agent", "学习计划需要数据库支持（未配置 DATABASE_URL）。")
        try:
            from app.todo import planner
            from app.todo.schemas import PlanRequest

            plan = planner.generate(config, PlanRequest(user_id=state["user_id"], target_roles=roles))
            m = plan.metrics
            weeks = m.weeks_est if m.weeks_est is not None else "?"
            prefix = f"按你关注的技能已为你锁定「{role_from_skill['role_name']}」目标。" if role_from_skill else ""
            summary = (
                f"{prefix}已为你生成「{plan.goal}」学习计划：{m.total_tasks} 个任务 / {len(plan.phases)} 个阶段，"
                f"预计约 {weeks} 周（{m.total_hours:.0f} 小时）。可到「学习计划」页查看与流转。"
            )
            artifacts = {
                "intent": "plan_generation",
                "plan_id": plan.plan_id,
                "goal": plan.goal,
                "total_tasks": m.total_tasks,
                "phase_count": len(plan.phases),
                "goto": {"page": "plan"},
            }
            return _done(summary, artifacts, "plan_agent", learning_plan=plan.model_dump())
        except Exception:  # noqa: BLE001
            logger.warning("plan_node 失败 user=%s", state.get("user_id"), exc_info=True)
            return _degraded("plan_agent", "学习计划生成暂时不可用，请稍后再试，或到「学习计划」页操作。")

    return node


# ---------------- 目标画像（方案第 5、6、8 节） ----------------

def _target_artifacts(intent: str, target) -> dict:
    return {"intent": intent, "target_profile": target.model_dump()}


def make_tech_requirement_node(config: Config) -> Callable[[dict], dict]:
    """tech_learning → TargetProfile（目标技能 + 前置/关联技能，来自技能关系图谱）。"""
    from app.agents import intent_parser
    from app.agents.target_profile import build_tech_target, summarize

    def node(state: dict) -> dict:
        params = state.get("intent_params") or {}
        target_skills = params.get("target_skills") or []
        if not target_skills:
            return _need_input(
                "tech_requirement_agent",
                "你想学习哪个技术或技能？例如："
                f"{intent_parser.list_skill_names(config, 4)}；也可以说「我想学 LangGraph」。",
            )
        try:
            target = build_tech_target(config, target_skills)
        except Exception:  # noqa: BLE001
            logger.warning("tech 目标画像构建失败", exc_info=True)
            return _degraded("tech_requirement_agent", "目标技能画像构建失败，请稍后再试。")
        return _done(
            summarize(target),
            _target_artifacts("tech_learning", target),
            "tech_requirement_agent",
            target_profile=target.model_dump(),
            user_goal=target.goal_name,
        )

    return node


def make_job_requirement_node(config: Config) -> Callable[[dict], dict]:
    """job_search → TargetProfile（直接复用岗位能力知识库 required_skills）。"""
    from app.agents import intent_parser
    from app.agents.target_profile import build_job_target, summarize

    def node(state: dict) -> dict:
        params = state.get("intent_params") or {}
        roles = params.get("target_roles") or []
        if not roles:
            return _need_input(
                "job_requirement_agent",
                "你想找哪个岗位？可选岗位："
                f"{intent_parser.list_role_names(config)}；也可以说「我想找 AI Agent 工程师」。",
            )
        try:
            target = build_job_target(config, roles[0])
        except Exception:  # noqa: BLE001
            logger.warning("job 目标画像构建失败", exc_info=True)
            return _degraded("job_requirement_agent", "岗位能力解析失败，请稍后再试。")
        if target is None:
            return _need_input(
                "job_requirement_agent",
                "没找到这个岗位，请换个说法，比如：AI 应用工程师 / Java 后端工程师。",
            )
        return _done(
            summarize(target),
            _target_artifacts("job_search", target),
            "job_requirement_agent",
            target_profile=target.model_dump(),
            user_goal=target.goal_name,
        )

    return node