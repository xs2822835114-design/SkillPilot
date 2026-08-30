"""TaskRefinementAgent：把已确定的 LearningTask 精炼成「可直接照着执行」的执行任务。

职责边界（方案「执行计划精炼 / ExecutionPlanRefiner」）：
- 只负责「怎么学、做什么、产出什么、如何验证」；
- 不重新规划学习路线、不改技能缺口结论、不重算工时；
- Planner → LearningPlan Skeleton → TaskRefinementAgent → Execution LearningPlan。

关键改进（解决「所有技能被套同一模板」）：
- 先由 Skill Classification（app.knowledge.learning_metadata）判定该技能属于什么学习对象
  （framework / library / api / mechanism / concept / pattern / architecture / language）；
- 再按 learning_mode 选择对应策略路径（MODE_PATHS）生成步骤；
- 机制类（checkpoint / state_management 等）在父框架中做实验，不安排「独立项目」；
- 只有 supports_standalone_project=true 才允许独立实现。
"""
from __future__ import annotations

import logging
from typing import Any

from app.config import Config
from app.domain.execution import ExecutionStep, RefinedTask, TaskRefinementInput
from app.knowledge import _json_source
from app.knowledge.learning_metadata import SkillLearningProfile, classify, path_for
from app.knowledge import resources_for

logger = logging.getLogger(__name__)


# ---------------- Tool（Skill Graph / 知识层提供事实） ----------------

def get_skill_context(config: Config, skill_id: str) -> dict:
    """Tool 1：返回技能的结构化学习元数据（分类 + 关系 + 学习策略约束）。"""
    return classify(config, skill_id).to_dict()


def get_learning_resources(config: Config, skill_name: str, topic: str = "", limit: int = 3) -> list[dict]:
    """Tool 2：获取该技能对应主题的可靠学习资源（决定放哪一步由 Agent 负责）。"""
    try:
        return [
            {"title": r.get("title") or "", "url": r.get("url") or "", "source": r.get("category") or "", "topic": topic}
            for r in resources_for(config, skill_name, limit=limit)
        ]
    except Exception:  # noqa: BLE001 - 资源缺失不阻断精炼
        return []


# ---------------- Agent ----------------

class TaskRefinementAgent:
    """执行计划精炼 Agent：单任务输入 → RefinedTask。"""

    name = "task_refinement_agent"

    def __init__(self, config: Config) -> None:
        self.config = config
        self._llm: Any = None

    def refine_task(self, inp: TaskRefinementInput) -> RefinedTask:
        profile = classify(self.config, inp.skill_id or inp.skill_name)
        resources = get_learning_resources(self.config, profile.skill_name, limit=3)
        if self.config.llm_enabled:
            out = self._refine_with_llm(inp, profile, resources)
            if out is not None:
                return out
        return self._refine_with_rules(inp, profile, resources)

    def _get_llm(self):
        if not self.config.llm_enabled:
            return None
        if self._llm is None:
            try:
                from langchain_openai import ChatOpenAI

                self._llm = ChatOpenAI(
                    model=self.config.llm_model,
                    base_url=self.config.llm_base_url,
                    api_key=self.config.llm_api_key,
                    temperature=0,
                )
            except Exception:  # noqa: BLE001
                logger.warning("langchain_openai 不可用，回退规则实现", exc_info=True)
                self._llm = False
        return self._llm if self._llm else None

    def _refine_with_llm(self, inp: TaskRefinementInput, profile: SkillLearningProfile, resources: list[dict]) -> RefinedTask | None:
        llm = self._get_llm()
        if not llm:
            return None
        try:
            from langchain_core.prompts import ChatPromptTemplate

            prompt = ChatPromptTemplate.from_messages(
                [("system", _SYSTEM_PROMPT), ("human", _HUMAN_TEMPLATE)]
            )
            chain = prompt | llm.with_structured_output(RefinedTask)
            result = chain.invoke(
                {
                    "task_id": inp.task_id,
                    "skill_id": inp.skill_id,
                    "skill_name": profile.skill_name,
                    "goal": inp.goal or "（未指定目标）",
                    "gap": inp.gap,
                    "estimated_hours": inp.estimated_hours,
                    "acceptance_criteria": inp.acceptance_criteria or "（沿用既有验收标准）",
                    "profile": _dump(profile.to_dict()),
                    "strategy": _dump([s.__dict__ for s in path_for(profile.learning_mode)]),
                    "resources": _dump(resources),
                }
            )
            out = result if isinstance(result, RefinedTask) else RefinedTask.model_validate(result)
            return _sanitize_refined(out, inp)
        except Exception:  # noqa: BLE001
            logger.warning("LLM 精炼失败，回退规则实现 task=%s", inp.task_id, exc_info=True)
            return None

    # ---------------- 规则兜底（按学习模式生成确定性执行计划） ----------------

    def _refine_with_rules(self, inp: TaskRefinementInput, profile: SkillLearningProfile, resources: list[dict]) -> RefinedTask:
        name = profile.skill_name or inp.skill_id
        parent = profile.parent_skill_name or "宿主框架"
        mode = profile.learning_mode
        concepts = profile.core_concepts or ["核心概念"]
        apis = profile.core_apis or []
        goal = inp.goal or f"该技能（{name}）的学习与掌握"
        # 机制型：明确落在父框架上下文中
        host = parent if mode.value in ("mechanism",) and parent else "相关工程"

        spec_list = _materialize(profile, goal)
        steps: list[ExecutionStep] = []
        for i, s in enumerate(spec_list, start=1):
            step_id = _step_id(i, s)
            minutes = _minutes_for(inp.estimated_hours, len(spec_list), i)
            steps.append(
                ExecutionStep(
                    step_id=step_id,
                    title=s["title"],
                    action=f"{s['action']}（{host}）" if mode.value in ("mechanism", "concept") and host != "相关工程" else s["action"],
                    instructions=s["instructions"],
                    deliverable=s["deliverable"],
                    verification=s["verification"],
                    estimated_minutes=minutes,
                    resources=resources[:1] if i == 1 else [],
                )
            )
        return RefinedTask(
            task_id=inp.task_id,
            title=f"学习并掌握 {name}",
            learning_objective=f"能够在场景中独立应用 {name} 的核心能力（{mode.value}）",
            acceptance_criteria=inp.acceptance_criteria or f"理解并掌握 {name} 的核心概念，能独立完成一个可运行示例",
            execution_steps=steps,
            total_estimated_minutes=sum(s.estimated_minutes for s in steps),
            is_refined=True,
        )


def _materialize(profile: SkillLearningProfile, goal: str) -> list[dict]:
    """把学习模式的策略路径 + 技能的真实概念/API 组合成具体可执行步骤。

    原则：
    - 机制/概念/API 类型不带独立项目阶段（stage.needs_standalone=False 时的「独立实现」被替换为
      「在宿主/host 中验证」）；
    - 步骤文案全部指向真实概念/API/父框架，不出现空泛的「掌握相关知识」。
    """
    name = profile.skill_name or profile.skill_id
    parent = profile.parent_skill_name or "宿主框架"
    concepts = profile.core_concepts or ["核心概念"]
    apis = profile.core_apis or []
    concept = concepts[0]
    api = apis[0] if apis else "核心接口"
    standalone_ok = profile.supports_standalone_project

    base = path_for(profile.learning_mode)
    out: list[dict] = []
    for j, spec in enumerate(base, start=1):
        last = j == len(base)
        if spec.needs_standalone and not standalone_ok:
            # 不支持独立项目 → 换成「在宿主/场景中验证与复盘」
            if profile.learning_mode.value in ("framework", "library", "pattern"):
                tail = _step_spec(
                    "场景验收",
                    f"在一个贴近「{goal}」的最小场景中使用 {name}（{concept}）验证整体效果",
                    _ins(name, f"把前面练过的 {concept} 串起来", goal),
                    f"符合验收标准的完整可运行结果",
                    f"不看示例能独立讲清如何用 {name} 解决「{goal}」里的问题",
                )
                out.append(tail)
                continue
            continue  # mechanism/api/concept 本就无补齐独立项目，直接跳过该阶段
        # 从 StageSpec 生成 step 文案
        start = spec.start.format(name=name, parent=parent, concept=concept, api=api, goal=goal)
        verify = spec.verify.format(name=name, parent=parent, concept=concept, api=api, goal=goal)
        title = _stage_title(profile.learning_mode, j, spec)
        out.append(
            _step_spec(
                title,
                start,
                _ins(name, concept, goal),
                _deliverable(profile.learning_mode, title, concept),
                verify,
            )
        )
    return out


def _stage_title(mode, j: int, spec) -> str:
    phrase = spec.goal
    if mode.value in ("mechanism", "concept"):
        return f"{mode.value}：{phrase}"
    return f"第{j}环：{phrase}"


def _step_spec(title: str, action: str, instructions: list[str], deliverable: str, verification: str) -> dict:
    return {
        "title": title, "action": action, "instructions": instructions,
        "deliverable": deliverable, "verification": verification,
    }


def _ins(name: str, concept: str, goal: str) -> list[str]:
    return [
        f"准备好 {name} 对应的最小运行环境",
        f"围绕 {concept} 写出可直接运行的核心代码",
        f"运行并记录结果，把它与「{goal}」联系起来",
    ]


def _deliverable(mode, title: str, concept: str) -> str:
    if "笔记" in title or "理解" in title or "认识" in title:
        return f"一页关于 {concept} 的学习笔记"
    if "实验" in title or "练习" in title or "调用" in title:
        return f"可运行的 {concept} 实验/示例"
    return f"体现 {concept} 的可运行小工程"


def _step_id(i: int, s: dict) -> str:
    return f"S{i}"


def _minutes_for(hours: float, n: int, i: int) -> int:
    total = int(hours * 60)
    if total < 2 * n:
        total = 2 * n
    base, rem = total // n, total % n
    return base + (1 if i <= rem else 0)


# ---------------- 服务：逐任务精炼整份计划 ----------------

def refine_learning_plan(config: Config, plan) -> "LearningPlan":
    """把 LearningPlan 里的每条任务迭代精炼为执行级步骤（best-effort）。

    不修改技能顺序 / 阶段 / 缺口结论，只填充 task.execution_steps 与 is_refined。
    """
    if plan is None:
        return plan
    agent = TaskRefinementAgent(config)
    for phase in plan.phases:
        for task in phase.tasks:
            try:
                name = _skill_name(config, task.skill_id)
                inp = TaskRefinementInput(
                    task_id=task.task_id,
                    skill_id=task.skill_id,
                    skill_name=name,
                    goal=plan.goal,
                    gap=max(1, round(task.estimated_hours / (config.plan_hours_per_level or 3))),
                    estimated_hours=task.estimated_hours,
                    acceptance_criteria=task.acceptance_criteria,
                    existing_steps=list(task.steps),
                )
                refined = agent.refine_task(inp)
                task.execution_steps = refined.execution_steps
                task.is_refined = True
            except Exception:  # noqa: BLE001
                logger.warning("精炼任务失败 task=%s", task.task_id, exc_info=True)
                continue
    return plan


def _skill_name(config: Config, skill_id: str) -> str:
    try:
        from app.knowledge import resolve_skill

        return (resolve_skill(config, skill_id) or {}).get("name", skill_id)
    except Exception:  # noqa: BLE001
        return skill_id


def _sanitize_refined(out: RefinedTask, inp: TaskRefinementInput) -> RefinedTask:
    steps = [s for s in (out.execution_steps or []) if s.title.strip()]
    if len(steps) > 10:
        steps = steps[:10]
    out.execution_steps = steps
    out.total_estimated_minutes = sum(s.estimated_minutes for s in steps)
    if not out.task_id:
        out.task_id = inp.task_id
    if not out.title:
        out.title = f"学习并掌握 {(inp.skill_name or inp.skill_id or '该技能')}"
    return out


def _dump(obj) -> str:
    try:
        import json

        return json.dumps(obj, ensure_ascii=False, default=str)
    except Exception:  # noqa: BLE001
        return str(obj)


_SYSTEM_PROMPT = """你是 SkillPilot 的 ExecutionPlanRefiner，把已经确定的一个学习技能转换为可直接执行的学习计划。

你绝不是把固定模板填满。你必须第一眼判断该技能属于哪类学习对象，再设计对应执行步骤。

## 一、禁止固定模板
禁止默认使用「概念学习 → 环境搭建 → 核心 API → 独立项目 → 验收」。
禁止因为有 API 就强行安排多个 API 练习；禁止因为任务有 4 小时就强行安排「独立项目」；
禁止把技能名称简单替换进固定句式。

## 二、先判断学习对象（skill_type / learning_mode）
你必须依据输入 profile 里的 skill_type、learning_mode、parent_skill、core_concepts、
core_apis、supports_standalone_project 判断它适合怎么学。

- mechanism（如 Checkpoint、State Management）：概念 → 最小实验 → 观察状态变化 → 参数/行为实验 → 场景应用 → 验收。不要默认要独立项目。
- api（如 LLM API、Tool Calling）：接口理解 → 最小调用 → 参数实验 → 错误/重试 → 真实调用 → 验收。不要写「搭建 XX 项目」。
- framework（如 LangGraph、LangChain）：核心抽象 → 最小程序 → 核心组件 → 组件组合 → 小项目 → 独立实现。
- library（如 SQLAlchemy）：核心对象 → 最小示例 → 典型 API → 数据/业务操作 → 框架集成 → 独立实现。
- concept（如 Retriever）：概念 → 对比 → 场景判断 → 小实验 → 应用判断 → 解释验收。
- pattern（如 RAG）：原理 → Pipeline → 局部实验 → 综合案例。
- architecture / language：分别按「分层→核心能力→组合→独立交付」和「语法→练习→综合→小项目」。

## 三、服从父技能关系
若 skill 是某框架的子能力（如 Checkpoint→LangGraph），学习必须建立在父框架上下文中，
不要虚构「Checkpoint 项目」，而应「在 LangGraph Graph 中验证 Checkpoint」。

## 四、独立项目不是必选项
仅当 supports_standalone_project=true 才允许安排独立实现。否则用父框架做实验、修改已有示例、
构造最小实验、完成局部功能、对已有系统验证。

## 五、围绕真实技术对象
步骤尽量指向真实概念 / API / 参数 / 运行行为 / 技术场景（使用 core_concepts 与 core_apis）。
禁止输出「理解核心概念」「掌握相关知识」「完成综合项目」这类不可执行的空话。

## 六、原子化
一个步骤只做一个主要动作；每步含 title / action / instructions / deliverable / verification / estimated_minutes。

## 七、步骤数量
4 小时任务通常 4~7 步；技能简单可 4 步，复杂可 7~8 步。禁止凑数造无意义步骤。

## 八、实践优先
能代码验证就先给可运行实验；机制就观察机制行为；API 就调用并看结果；Framework 就构建真实功能。

## 九、时间必须真实
所有 estimated_minutes 之和接近 estimated_hours。

## 十、最终要求
用户看到步骤后能立即知道「现在打开电脑，我具体该做什么」。最终只输出符合
RefinedTask / ExecutionStep schema 的结构化 JSON。"""

_HUMAN_TEMPLATE = """请精炼以下学习任务：
- task_id: {task_id}
- skill: {skill_name}（id: {skill_id}）
- 用户目标: {goal}
- 缺口等级: {gap}
- 预估工时(h): {estimated_hours}
- 验收标准: {acceptance_criteria}

技能学习元数据（Skill Classification + 关系，来自 Skill Graph）：
{profile}

配套学习策略路径（作为参考，可据实际调整，不要机械照抄）：
{strategy}

可用学习资源（决定放哪一步由你负责）：
{resources}

请输出 RefinedTask（execution_steps 为原子化、可验证、贴合该技能学习方式的步骤）。"""


# 供 explain.build_steps 等模块引用的简版分类（避免循环依赖）
_build_skeleton_cache__: dict = {}


def build_steps_fallback(config: Config, name: str, skill_id: str, delta: int) -> list[str]:
    """按学习模式返回粗粒度骨架 steps（planner 的 `steps` 字段）；机制/API 类不再套项目模板。

    这是对原固定模板 build_steps 的替代：先分类再给骨架，仍是「阶段目标」级别的粗粒度文案，
    真正的执行级细节交给 Refiner（execution_steps）。
    """
    profile = classify(config, skill_id or name)
    goal = f"{name} 的学习与掌握"
    out: list[str] = []
    for s in _materialize(profile, goal):
        out.append(s["title"] + "：" + s["action"])
    return out or [f"学习并掌握 {name}"]