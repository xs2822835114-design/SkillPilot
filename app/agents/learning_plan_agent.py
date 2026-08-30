"""LearningPlanAgent（直出学习计划）：TargetProfile → LearningPlan。

职责边界（方案「Agent 理解决策 / 数据结构描述事实 / Skill Knowledge 提供事实」）：
- LLM 负责「生成计划内容」（目标、阶段、任务的步骤与验收）；
- Pydantic 负责「约束结构」；
- Skill Knowledge（app.knowledge.learning_metadata 的技能分类）负责「提供事实」，
  决定机制/API/框架/概念类技能该怎么学，避免 LLM 把所有技能套成同一模板。

触发路径（learning_plan_mode="direct"，默认）：
  tech/job requirement（target_profile）
      → learning_plan_node（本 Agent）
      → LearningPlan（phases / tasks / estimated_hours / acceptance_criteria / steps / execution_steps）
      → 落库（todo_store）→ 前端「学习计划」页

访谈链路（learning_plan_mode="interview"）作为可选「精准模式」保留，不由本模块承担。
"""

from __future__ import annotations

import json
import logging
import math
import uuid
from typing import Any

from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field

from app.config import Config
from app.domain import TargetProfile
from app.todo.schemas import (
    PLAN_IN_PROGRESS,
    LearningPhase,
    LearningPlan,
    PlanMetrics,
    LearningTask,
)

logger = logging.getLogger(__name__)


# ---------------- LLM 结构化输出契约（只约束计划骨架，执行步骤交由 Refiner 细化） ----------------

class _LLMTask(BaseModel):
    skill_id: str = ""
    title: str
    estimated_hours: float = Field(default=4.0, ge=1.0, le=24.0)
    acceptance_criteria: str = ""
    steps: list[str] = Field(default_factory=list)


class _LLMPhase(BaseModel):
    title: str = ""
    order: int = 0
    tasks: list[_LLMTask] = Field(default_factory=list)


class _LLMPlanSkeleton(BaseModel):
    goal: str = ""
    phases: list[_LLMPhase] = Field(default_factory=list)


# ---------------- 图节点 ----------------

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


def make_learning_plan_node(config: Config) -> Any:
    """图节点：把 target_profile 直接转成结构化 LearningPlan（默认路径）。"""

    def node(state: dict) -> dict:
        target_raw = state.get("target_profile")
        if not target_raw:
            return _degraded(
                "learning_plan_agent",
                "目标画像缺失，无法生成学习计划。请先说明你想学习的技术或目标岗位。",
            )
        try:
            target = TargetProfile.model_validate(target_raw)
            plan = generate(config, target, state.get("user_id") or "")
            m = plan.metrics
            weeks = m.weeks_est if m.weeks_est is not None else "?"
            summary = (
                f"已为你生成「{plan.goal}」学习计划：{len(plan.phases)} 个阶段 / "
                f"{m.total_tasks} 个任务，预计约 {m.total_hours:.0f} 小时（{weeks} 周）。"
                "每个技能的每一步、验收与执行细节都已就绪，可到「学习计划」页查看。"
            )
            artifacts: dict[str, Any] = {
                "intent": state.get("intent") or "plan_generation",
                "target_profile": target.model_dump(),
                "plan_id": plan.plan_id,
                "goal": plan.goal,
                "total_tasks": m.total_tasks,
                "phase_count": len(plan.phases),
                "learning_plan": plan.model_dump(),
                "goto": {"page": "plan"},
            }
            return _done(
                summary,
                artifacts,
                "learning_plan_agent",
                learning_plan=plan.model_dump(),
            )
        except Exception:  # noqa: BLE001
            logger.warning("learning_plan_node 失败 user=%s", state.get("user_id"), exc_info=True)
            return _degraded("learning_plan_agent", "学习计划生成暂时不可用，请稍后再试，或到「学习计划」页操作。")

    return node


# ---------------- 技能排序（Skill Knowledge 拓扑） ----------------

def _order_skills(config: Config, requirements: list) -> list:
    """按前置拓扑排序需求技能（target 在前、其余按父链），保证先学前置。"""
    try:
        from app.engines import build_learning_path

        path = build_learning_path(config, [r.skill_id for r in requirements])
        idx = {sid: i for i, sid in enumerate(path)}
        return sorted(requirements, key=lambda r: (r.skill_id not in idx, idx.get(r.skill_id, 2 ** 31), r.source != "target"))
    except Exception:  # noqa: BLE001
        return sorted(requirements, key=lambda r: (r.source != "target", -r.weight))


def _hours_for(required_level: int) -> float:
    return 4.0 + max(0, (int(required_level) or 1) - 1) * 2.0


# ---------------- 生成入口 ----------------

def generate(config: Config, target: TargetProfile, user_id: str) -> LearningPlan:
    """GenerateLearningPlan 服务：LLM 直出优先，失败/关闭回退规则骨架，最后落库 + 细化步骤。"""
    ordered = _order_skills(config, target.skills)
    plan: LearningPlan | None = None
    try:
        if config.learning_plan_llm_enabled and config.llm_enabled:
            plan = _llm_plan(config, target, user_id, ordered)
    except Exception:  # noqa: BLE001
        logger.warning("LLM 学习计划生成失败，回退规则骨架", exc_info=True)
        plan = None
    if plan is None:
        plan = _rule_plan(config, target, user_id, ordered)
    _finalize_metrics(plan)
    _persist_and_refine(config, target, plan)
    return plan


# ---------------- LLM 规划（Skill Knowledge 提供事实） ----------------

def _llm_plan(config: Config, target: TargetProfile, user_id: str, ordered: list) -> LearningPlan | None:
    from langchain_openai import ChatOpenAI

    profile_lines = _skill_metadata(config, ordered)
    llm = ChatOpenAI(
        model=config.llm_model,
        base_url=config.llm_base_url,
        api_key=config.llm_api_key,
        temperature=0.4,
    )
    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", _SYSTEM_PROMPT),
            (
                "human",
                "用户目标：{goal}\n"
                "技能清单（含 Skill Knowledge 分类，按建议学习顺序给出）：\n{skills}\n\n"
                "只输出一段合法 JSON（不要 markdown 代码块），结构如下：\n"
                '{json_schema}\n'
                "要求：每个 task 含 title / estimated_hours / acceptance_criteria / steps(4~8 条可执行步骤)；"
                "phase 的 task 需自带 skill_id（取技能清单里的 id）。",
            ),
        ]
    )
    schema = json.dumps(
        {
            "goal": "一句话目标",
            "phases": [
                {
                    "title": "阶段标题",
                    "order": 1,
                    "tasks": [
                        {"skill_id": "技能id", "title": "任务标题", "estimated_hours": 4.0,
                         "acceptance_criteria": "可验证的验收标准", "steps": ["步骤1", "步骤2", "..."]}
                    ],
                }
            ],
        },
        ensure_ascii=False,
    )
    res = (prompt | llm).invoke({"goal": target.goal_name, "json_schema": schema, "skills": "\n".join(profile_lines)})
    text = (res.content if hasattr(res, "content") else str(res)).strip()
    data = json.loads(_extract_json(text))
    skel = _LLMPlanSkeleton.model_validate(data)
    if not skel.phases:
        return None
    return _skeleton_to_plan(config, target, user_id, skel)


def _extract_json(text: str) -> str:
    """从 LLM 输出里截取第一个 { 到最后一个 } 的 JSON 片段，兼容带代码块污染。"""
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = stripped.strip("`")
        if stripped.startswith("json"):
            stripped = stripped[4:]
    start = stripped.find("{")
    end = stripped.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("LLM 未返回合法 JSON")
    return stripped[start : end + 1]


def _skill_metadata(config: Config, ordered: list) -> list[str]:
    """每个技能 → 结构化事实（skill_type / learning_mode / parent / concepts / apis / practices）。"""
    from app.knowledge.learning_metadata import classify

    lines: list[str] = []
    for r in ordered:
        try:
            p = classify(config, r.skill_id)
            lines.append(
                "- skill: {}（id {}）\n"
                "  skill_type/learning_mode: {} / {}\n"
                "  parent_skill: {}\n"
                "  supports_standalone_project: {}\n"
                "  core_concepts: [{}]\n"
                "  core_apis: [{}]\n"
                "  practice_context: [{}]\n"
                "  required_level: {}".format(
                    p.skill_name, r.skill_id, p.skill_type, p.learning_mode.value,
                    p.parent_skill_name or "（无，独立技能）", p.supports_standalone_project,
                    "、".join(p.core_concepts or []), "、".join(p.core_apis or []),
                    "、".join(p.practice_context or []), r.required_level,
                )
            )
        except Exception:  # noqa: BLE001 - 单个技能元数据缺失不阻断整体
            lines.append(f"- skill: {(r.skill_name or r.skill_id)}（id {r.skill_id}）")
    return lines


def _skeleton_to_plan(config: Config, target: TargetProfile, user_id: str, skel: _LLMPlanSkeleton) -> LearningPlan:
    name_by_id = {s.skill_id: s.skill_name for s in target.skills}
    phase_list: list[LearningPhase] = []
    task_list: list[LearningTask] = []
    global_idx = 0
    for ph in sorted(skel.phases, key=lambda p: p.order or 0):
        ftasks: list[LearningTask] = []
        for t in ph.tasks:
            global_idx += 1
            title = t.title or f"学习并掌握 {name_by_id.get(t.skill_id, t.skill_id)}"
            ftasks.append(
                LearningTask(
                    task_id=f"PLAN_{uuid.uuid4().hex[:8]}-T{global_idx:02d}",
                    skill_id=t.skill_id,
                    title=title,
                    estimated_hours=t.estimated_hours,
                    status="pending",
                    acceptance_criteria=t.acceptance_criteria or f"理解并掌握 {name_by_id.get(t.skill_id, t.skill_id)} 的核心概念，能完成一个可运行示例",
                    steps=list(t.steps),
                    required=True,
                    order=global_idx,
                )
            )
        if ftasks:
            phase_list.append(
                LearningPhase(
                    phase_id=f"P{len(phase_list) + 1}",
                    title=ph.title or "学习路线",
                    order=len(phase_list) + 1,
                    skill_ids=[t.skill_id for t in ftasks],
                    tasks=ftasks,
                )
            )
            task_list.extend(ftasks)
    if not phase_list:  # 兜底：LLM 没分阶段时也要有可执行内容
        raise ValueError("LLM 未生成有效阶段")
    return LearningPlan(
        plan_id=_new_plan_id(),
        user_id=user_id,
        goal=skel.goal or f"{target.goal_name} 学习达成计划",
        source_role=target.goal_type or "",
        status=PLAN_IN_PROGRESS,
        is_llm_enhanced=True,
        phases=phase_list,
    )


# ---------------- 规则骨架（LLM 关闭/失败时兜底） ----------------

def _rule_plan(config: Config, target: TargetProfile, user_id: str, ordered: list) -> LearningPlan:
    from app.todo.explain import build_acceptance, build_steps

    phases: list[LearningPhase] = []
    global_idx = 0
    for i, r in enumerate(ordered, start=1):
        global_idx += 1
        name = r.skill_name or r.skill_id
        steps = build_steps(config, name, r.skill_id, r.required_level or 1)
        task = LearningTask(
            task_id=f"{_new_plan_id()}-T{global_idx:02d}",
            skill_id=r.skill_id,
            title=f"学习并掌握 {name}",
            estimated_hours=_hours_for(r.required_level),
            status="pending",
            acceptance_criteria=build_acceptance(name, r.required_level or 1),
            steps=list(steps),
            required=r.source == "target",
            order=global_idx,
        )
        phases.append(
            LearningPhase(
                phase_id=f"P{i}",
                title=name,
                order=i,
                skill_ids=[r.skill_id],
                tasks=[task],
            )
        )
    return LearningPlan(
        plan_id=_new_plan_id(),
        user_id=user_id,
        goal=f"{target.goal_name} 学习达成计划",
        source_role=target.goal_type or "",
        status=PLAN_IN_PROGRESS,
        is_llm_enhanced=False,
        phases=phases,
    )


# ---------------- 收尾：指标 + 落库 + 细化执行步骤 ----------------

def _finalize_metrics(plan: LearningPlan) -> None:
    total_hours = sum(t.estimated_hours for ph in plan.phases for t in ph.tasks)
    total_tasks = sum(len(ph.tasks) for ph in plan.phases)
    weeks = math.ceil(total_hours / 5.0) if total_hours > 0 else None
    plan.metrics = PlanMetrics(
        total_hours=round(total_hours, 1),
        total_tasks=total_tasks,
        done_tasks=0,
        weeks_est=weeks,
    )


def _persist_and_refine(config: Config, target: TargetProfile, plan: LearningPlan) -> None:
    """best-effort 落库供「学习计划」页读取，并用 ExecutionPlanRefiner 补齐原子步骤。"""
    try:
        from app.todo import todo_store

        if not config.database_url:
            raise RuntimeError("DATABASE_URL 未配置，跳过落库")
        skill_ids = [sid for ph in plan.phases for sid in ph.skill_ids]
        todo_store.create_plan(
            config, plan,
            report={"target": target.goal_name, "skill_ids": skill_ids},
            skill_ids=skill_ids,
        )
    except Exception:  # noqa: BLE001 - 落库失败不阻断主流程
        logger.warning("learning_plan 落库失败", exc_info=True)
    try:
        from app.agents.task_refinement import refine_learning_plan

        refine_learning_plan(config, plan)
    except Exception:  # noqa: BLE001
        logger.warning("learning_plan 执行步骤精炼失败", exc_info=True)


def _new_plan_id() -> str:
    return f"PLAN_{uuid.uuid4().hex[:12]}"


# ---------------- Prompt（与 Skill Knowledge 分类对齐，禁止统一模板） ----------------

_SYSTEM_PROMPT = """你是一名技术学习规划师（SkillPilot 的 LearningPlanAgent）。

根据用户学习目标和「技能清单」（含 Skill Knowledge 分类），生成一份真正可执行、可验收的个性化学习计划。

## 你必须依据每个技能的 skill_type / learning_mode / parent / supports_standalone_project 决定怎么学，禁止把所有技能套成同一套固定模板（概念→环境→API→项目→验收）：

- mechanism（如 Checkpoint、State Management）：以「最小实验、观察行为/状态变化、参数/行为实验、在父框架上下文中验证」为主，不安排「独立项目」。
- api（如 LLM API、Tool Calling）：以「最小调用、参数、异常处理、实际应用」为主，不写「搭建 XX 项目」。
- framework（如 LangGraph、LangChain）：以「核心抽象、组件使用、组件组合、实际项目」为主。
- library（如 SQLAlchemy）：以「核心对象、最小示例、典型操作、框架集成」为主。
- concept（如 Retriever）：以「概念理解、边界对比、场景判断、小实验」为主。
- pattern（如 RAG）：以「原理、最小 Pipeline、局部实验、综合案例」为主。
- architecture / language：分别按「分层→核心能力→组合→独立交付」和「语法→练习→综合→小项目」。

优先保证：父技能先于子技能，前置先于依赖。

## 每个 task 必须包含：
1. 学习目标（title）
2. 预计时间（estimated_hours，1~24 小时，机制/API 类偏小）
3. 验收标准（acceptance_criteria，可验证、能看结果）
4. 4~8 个可执行步骤（steps，每一条是"做什么/怎么操作"的可执行指令，指向真实概念/API/场景）

## 约束
- 禁止为了凑步骤生成无意义内容；
- 禁止生成"掌握相关知识""理解核心概念"这类不可执行的空话；
- 机制/API 类技能不得虚构"独立项目"，应在父框架或最小实验里验证。
"""


# 供其它模块零依赖读取骨架（避免重复实现）
def build_steps_direct(config: Config, name: str, skill_id: str, required_level: int) -> list[str]:
    from app.todo.explain import build_steps

    return build_steps(config, name, skill_id, required_level)


def dump_json(obj) -> str:
    try:
        return json.dumps(obj, ensure_ascii=False, default=str)
    except Exception:  # noqa: BLE001
        return str(obj)