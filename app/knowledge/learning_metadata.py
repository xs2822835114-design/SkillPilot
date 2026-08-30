"""技能学习元数据（Skill Classification / Learning Mode）。

这是「技能 → 学习策略」的中间层，解决用户反馈的根本问题：
此前所有技能都被 `build_steps` 塞进同一套「概念→环境→API→项目→验收」模板，
现在先回答两件事：
  1. 这个技能是什么（skill_type / domain / parent_skill）；
  2. 它应该怎么学（learning_mode + 配套策略路径）。

数据来源原则（与整体架构一致）：
- 父技能 / 核心子能力 / 前置：来自 Skill Graph（composite_of / requires / related），不靠 LLM 猜；
- skill_type / learning_mode / core_concepts / core_apis / practice_context：优先取人工整理的
  元数据表；未覆盖的技能由启发式推断兜底，保证系统对任一技能都能给出合理策略。

每种 learning_mode 对应一条「策略路径」（MODE_PATHS）：形如
    {stage, goal, action_phrase, verify_phrase, needs_standalone}
供 ExecutionPlanRefiner 的规则实现按类型生成原子步骤；LLM 路径也以此为约束，
确保「Mechanism 不做独立项目、API 不搭工程、Framework 才做小项目」。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from app.config import Config
from app.knowledge import parent_skills, prerequisites, relations, resolve_skill


class LearningMode(str, Enum):
    CONCEPT = "concept"
    MECHANISM = "mechanism"
    API = "api"
    FRAMEWORK = "framework"
    LIBRARY = "library"
    PATTERN = "pattern"
    ARCHITECTURE = "architecture"
    LANGUAGE = "language"


@dataclass
class StageSpec:
    """策略路径中的一个环节：描述「这一步该做什么」与「怎么验证」，不含具体技能名。"""

    goal: str          # 这一步要达成的目标（动词短语）
    start: str         # 操作入口（含 {name}/{parent}/{concept}/{api} 占位）
    verify: str        # 怎样验证完成（含 {name} 占位）
    needs_standalone: bool = False  # 是否允许独立项目/独立实现


class SkillLearningProfile:
    """技能学习元数据：classification + learning_mode + 策略路径。"""

    __slots__ = (
        "skill_id", "skill_name", "domain", "skill_type",
        "learning_mode", "parent_skill_id", "parent_skill_name",
        "core_concepts", "core_apis", "supports_standalone_project",
        "prerequisites", "related_skills", "practice_context",
    )

    def __init__(self, **kw: Any) -> None:
        for k in self.__slots__:
            setattr(self, k, kw.get(k))

    def to_dict(self) -> dict:
        return {k: getattr(self, k) for k in self.__slots__}


# ---------------- 人工整理的元数据（按 skill_id，未覆盖的走启发式兜底） ----------------

_CURATED: dict[str, dict] = {
    "langgraph": {
        "skill_type": "framework", "learning_mode": LearningMode.FRAMEWORK,
        "supports_standalone_project": True,
        "core_concepts": ["State", "Node", "Edge", "Graph", "Checkpoint"],
        "core_apis": ["StateGraph", "add_node", "add_edge", "compile", "checkpointer"],
        "practice_context": ["multi-turn agent", "conditional routing", "stateful workflow"],
    },
    "langchain": {
        "skill_type": "framework", "learning_mode": LearningMode.FRAMEWORK,
        "supports_standalone_project": True,
        "core_concepts": ["LCEL", "Chain", "Tool", "Model", "Runnable"],
        "core_apis": ["ChatPromptTemplate", "RunnableSequence", "bind_tools"],
        "practice_context": ["agent pipeline", "tool orchestration", "RAG glue"],
    },
    "rag": {
        "skill_type": "pattern", "learning_mode": LearningMode.PATTERN,
        "supports_standalone_project": True,
        "core_concepts": ["Chunk", "Embedding", "Vector Store", "Retriever", "Generation"],
        "core_apis": ["chunker", "embed", "retriever", "chain.invoke"],
        "practice_context": ["document QA", "knowledge base", "retrieval pipeline"],
    },
    "tool_calling": {
        "skill_type": "api", "learning_mode": LearningMode.API,
        "supports_standalone_project": False,
        "core_concepts": ["function/tool schema", "tool binding", "tool result loop"],
        "core_apis": ["bind_tools", "PydanticToolsParser", "invoke"],
        "practice_context": ["agent tool use", "function calling chain"],
    },
    "sqlalchemy": {
        "skill_type": "library", "learning_mode": LearningMode.LIBRARY,
        "supports_standalone_project": True,
        "core_concepts": ["Engine", "Connection", "Session", "ORM", "Transaction"],
        "core_apis": ["create_engine", "sessionmaker", "declarative_base", "commit", "rollback"],
        "practice_context": ["ORM modeling", "CRUD", "FastAPI integration"],
    },
    "checkpoint": {
        "skill_type": "mechanism", "learning_mode": LearningMode.MECHANISM,
        "parent_skill_id": "langgraph",
        "supports_standalone_project": False,
        "core_concepts": ["checkpoint", "checkpointer", "thread_id", "state persistence"],
        "core_apis": ["checkpointer", "MemorySaver", "get_state", "update_state"],
        "practice_context": ["stateful graph", "conversation resume", "multi-thread isolation"],
    },
    "state_management": {
        "skill_type": "mechanism", "learning_mode": LearningMode.MECHANISM,
        "supports_standalone_project": False,
        "core_concepts": ["state definition", "state transition", "partial update", "consistency"],
        "core_apis": [],
        "practice_context": ["node-to-node state flow"],
    },
    "retriever": {
        "skill_type": "concept", "learning_mode": LearningMode.CONCEPT,
        "supports_standalone_project": False,
        "core_concepts": ["retrieval", "relevance ranking", "top-k"],
        "core_apis": [],
        "practice_context": ["document retrieval"],
    },
    "embedding": {
        "skill_type": "api", "learning_mode": LearningMode.API,
        "supports_standalone_project": False,
        "core_concepts": ["embedding model", "vector representation", "similarity"],
        "core_apis": ["embed_query"],
        "practice_context": ["vector search"],
    },
    "向量基础": {
        "skill_type": "concept", "learning_mode": LearningMode.CONCEPT,
        "supports_standalone_project": False,
        "core_concepts": ["vector", "distance", "similarity"],
        "core_apis": [],
        "practice_context": [],
    },
    "llm_api": {
        "skill_type": "api", "learning_mode": LearningMode.API,
        "supports_standalone_project": False,
        "core_concepts": ["message", "chat completion", "temperature", "structured output"],
        "core_apis": ["ChatOpenAI", "invoke", "with_structured_output"],
        "practice_context": ["chatbot", "agent backend call"],
    },
    "python": {
        "skill_type": "language", "learning_mode": LearningMode.LANGUAGE,
        "supports_standalone_project": True,
        "core_concepts": ["syntax", "data structures", "functions", "modules"],
        "core_apis": ["builtins", "packages", "venv"],
        "practice_context": ["scripting", "small project"],
    },
    "node_graph_编排": {
        "skill_type": "mechanism", "learning_mode": LearningMode.MECHANISM,
        "parent_skill_id": "langgraph",
        "supports_standalone_project": False,
        "core_concepts": ["node", "edge", "conditional routing", "graph execution"],
        "core_apis": ["add_node", "add_edge", "add_conditional_edges"],
        "practice_context": ["graph workflow", "routing"],
    },
    "postgresql": {
        "skill_type": "library", "learning_mode": LearningMode.LIBRARY,
        "supports_standalone_project": True,
        "core_concepts": ["table", "index", "transaction", "SQL"],
        "core_apis": ["CREATE/TABLE", "SELECT", "EXPLAIN"],
        "practice_context": ["data modeling", "query tuning"],
    },
    "redis": {
        "skill_type": "library", "learning_mode": LearningMode.LIBRARY,
        "supports_standalone_project": True,
        "core_concepts": ["data structures", "persistence", "cluster"],
        "core_apis": ["SET/GET", "HSET", "EXPIRE"],
        "practice_context": ["cache", "rate limit"],
    },
    "kubernetes": {
        "skill_type": "architecture", "learning_mode": LearningMode.ARCHITECTURE,
        "supports_standalone_project": True,
        "core_concepts": ["Pod", "Deployment", "Service", "Ingress"],
        "core_apis": ["kubectl", "manifest"],
        "practice_context": ["deploy", "scaling"],
    },
    "docker": {
        "skill_type": "library", "learning_mode": LearningMode.LIBRARY,
        "supports_standalone_project": True,
        "core_concepts": ["image", "container", "compose"],
        "core_apis": ["build", "run", "compose up"],
        "practice_context": ["containerize app"],
    },
}

# 启发式推断：skill_type → learning_mode / supports_standalone_project
_KEYWORD_MODE: list[tuple[list[str], str, bool]] = [
    (["framework", "graph", "chain", "platform", "编排框架", "框架"], "framework", True),
    (["library", "orm", "sdk"], "library", True),
    (["api", "调用", "接口"], "api", False),
    (["mechanism", "机制", "checkpoint", "持久化", "transaction"], "mechanism", False),
    (["pattern", "rag", "架构模式"], "pattern", True),
    (["architecture", "架构", "microservices", "微服务", "kubernetes"], "architecture", True),
    (["concept", "概念", "基础", "understanding"], "concept", False),
    (["language", "语言"], "language", True),
]
_DEFAULT_MODE = "library"


# ---------------- 策略路径（每种 learning_mode 一个） ----------------

# 占位：{name}=技能名，{parent}=父技能名，{concept}=择一核心概念，{api}=择一核心 API
MODE_PATHS: dict[LearningMode, list[StageSpec]] = {
    LearningMode.MECHANISM: [
        StageSpec("理解机制要解决的问题", "先运行最小宿主案例，观察没有该机制时的失效行为（涉及 {parent}）", "能解释为什么默认行为做不到这件事（对比笔记）"),
        StageSpec("最小接入实验", "在一个最小 {parent} 案例中接入该机制，验证其生效", "程序运行后确实出现了该机制带来的新行为"),
        StageSpec("观察内部状态变化", "改动输入，观察 {concept} 如何变化并记录", "能讲清触发条件与状态变化的对应关系"),
        StageSpec("参数/行为实验", "逐个调整关键参数，观察行为差异（涉及 {api}）", "能说明参数与行为的关联，并给出取舍"),
        StageSpec("场景应用", "在贴近「{goal}」的场景中应用该机制验证", "在真实场景下机制按预期工作"),
    ],
    LearningMode.API: [
        StageSpec("浏览接口", "读完 {name} 的接口文档，列出核心方法与签名（涉及 {api}）", "能列举主要方法及其入参/返回"),
        StageSpec("最小调用", "写一段最小代码完成一次真实调用，打印结果", "最小调用成功并输出结果"),
        StageSpec("参数实验", "调整关键参数（{concept}），对比输出差异", "能说明每个参数的作用"),
        StageSpec("错误处理与重试", "构造失败场景，实现错误处理/重试，观察行为", "失败能优雅处理并恢复"),
        StageSpec("贴合场景调用", "在一次贴近「{goal}」的真实调用中使用 {name}", "在场景中调用成功并达到目的"),
    ],
    LearningMode.FRAMEWORK: [
        StageSpec("理解核心抽象", "梳理 {name} 的核心抽象与分工（涉及 {concept}）", "能解释各部分如何协作"),
        StageSpec("跑通最小程序", "用最少的代码让 {name} 运转起来（Hello World）", "最小程序运行成功，理解每一行"),
        StageSpec("逐个使用核心组件", "分别实现 {concept} 的每个组成，验证各自作用", "每个组件都能独立演示"),
        StageSpec("组件组合", "把 {concept} 组合成一个完整流程", "组合流程能整体运行"),
        StageSpec("构建小项目", "用它搭一个贴近「{goal}」的可运行小项目", "小项目完成并演示核心能力", needs_standalone=True),
    ],
    LearningMode.LIBRARY: [
        StageSpec("认识核心对象", "读 {name} 文档确认核心对象职责（涉及 {api}）", "能讲清核心对象各自干什么"),
        StageSpec("最小示例", "写一段最小代码跑通 {name} 的基础流程", "最小示例运行成功"),
        StageSpec("典型能力练习", "完成一组典型操作：数据读写/CRUD（{concept}）", "各操作均可运行验证"),
        StageSpec("框架集成", "把 {name} 集成进宿主框架（{parent}）的局部流程", "集成后功能正常"),
        StageSpec("独立实现", "脱离教程独立实现一个可运行工程", "不复制教程也能独立完成", needs_standalone=True),
    ],
    LearningMode.PATTERN: [
        StageSpec("理解原理", "弄清 {name} 解决什么问题、核心组成部分", "能讲清模式原理与适用边界"),
        StageSpec("搭建最小 Pipeline", "实现一条最小 {name} 数据流", "最小流水线跑通"),
        StageSpec("局部实验", "对某个环节做参数/替换实验，观察对整体的影响", "能说明改动产生了什么差异"),
        StageSpec("综合案例", "用一个贴近「{goal}」的综合案例验证 {name}", "综合案例整体可用"),
    ],
    LearningMode.CONCEPT: [
        StageSpec("理解概念", "读资料弄清 {name} 的核心定义与作用", "能用一句话讲清它是什么"),
        StageSpec("与相邻概念对比", "对比 {name} 与相关概念，说清边界", "能列出对比维度与差异"),
        StageSpec("场景判断", "给出一系列场景，判断何时该用 {name}", "能按场景做出正确取舍"),
        StageSpec("小实验验证", "做一个最小实验观察 {name} 在场景中的表现", "实验验证了概念预期"),
    ],
    LearningMode.LANGUAGE: [
        StageSpec("掌握基础语法", "系统过一遍 {name} 基础语法，边看边写小片段", "能不看文档写出基础代码"),
        StageSpec("日常小练习", "完成 5~10 个针对语法/数据结构的练习", "每个练习独立运行通过"),
        StageSpec("综合练习", "做一个覆盖多数语法特性的综合练习", "综合练习通过并注释关键点"),
        StageSpec("小项目", "用 {name} 完成一个贴近「{goal}」的小项目", "小项目可运行并交付", needs_standalone=True),
    ],
    LearningMode.ARCHITECTURE: [
        StageSpec("理解整体/分层", "弄清 {name} 的架构分层与核心组件（涉及 {concept}）", "能画出整体架构图"),
        StageSpec("最小部署/运行", "搭一个可运行的最小 {name} 环境", "环境可启动并工作"),
        StageSpec("核心能力演练", "逐个实践核心组件（{api}），验证其作用", "每个能力都有运行证据"),
        StageSpec("组合打磨", "把组件组合成一套满足「{goal}」的最小系统", "系统能跑通关键路径"),
        StageSpec("独立交付", "独立完成一套可运行的小系统并复盘", "不依赖教程能重建", needs_standalone=True),
    ],
}


def _record(spec: StageSpec, name: str, parent: str, concept: str, api: str, goal: str) -> dict:
    """把 StageSpec + 占位替换成一条可执行步骤描述（供规则实现生成 ExecutionStep）。"""
    return {
        "goal": spec.goal,
        "start": spec.start.format(name=name, parent=parent, concept=concept, api=api, goal=goal),
        "verify": spec.verify.format(name=name, parent=parent, concept=concept, api=api, goal=goal),
        "needs_standalone": spec.needs_standalone,
    }


def classify(config: Config, skill_id: str) -> SkillLearningProfile:
    """为技能生成学习元数据：人工表优先，未覆盖则启发式推断。"""
    node = resolve_skill(config, skill_id) or {"id": skill_id, "name": skill_id, "domain": None}
    name = node.get("name") or skill_id
    curated = _CURATED.get(skill_id) or _CURATED.get(name)
    parents = parent_skills(config, skill_id)
    parent_id = (curated or {}).get("parent_skill_id") or (parents[0] if parents else None)

    if curated:
        mode = curated["learning_mode"]
        ptype = curated.get("skill_type", mode.value)
        concepts = curated.get("core_concepts") or []
        apis = curated.get("core_apis") or []
        standalone = curated.get("supports_standalone_project", mode in (LearningMode.FRAMEWORK, LearningMode.LIBRARY, LearningMode.LANGUAGE, LearningMode.PATTERN, LearningMode.ARCHITECTURE))
        practice = curated.get("practice_context") or []
    else:
        mode, ptype, standalone = _infer(name)
        concepts = _components(config, skill_id)
        apis = []
        practice = []
        # 有父技能的子能力倾向机制型实验；独立（非父下）的框架/库才做项目
        if parent_id:
            mode, ptype, standalone = LearningMode.MECHANISM, "mechanism", False

    parent_name = ""
    if parent_id:
        pr = resolve_skill(config, parent_id)
        parent_name = (pr or {}).get("name") or parent_id

    core_concepts = concepts or (["核心概念"] if not curated else ["核心概念"])
    core_apis = apis or (curated and curated.get("core_apis")) or []
    return SkillLearningProfile(
        skill_id=skill_id,
        skill_name=name,
        domain=node.get("domain"),
        skill_type=ptype,
        learning_mode=mode,
        parent_skill_id=parent_id,
        parent_skill_name=parent_name,
        core_concepts=core_concepts,
        core_apis=core_apis,
        supports_standalone_project=standalone,
        prerequisites=[resolve_skill(config, p).get("name") if resolve_skill(config, p) else p for p in prerequisites(config, skill_id)],
        related_skills=[resolve_skill(config, r).get("name") if resolve_skill(config, r) else r for r in relations(config, skill_id)["related"]],
        practice_context=practice,
    )


def _infer(name: str) -> tuple[LearningMode, str, bool]:
    low = re.sub(r"[\s/]+", " ", name).lower()
    for kws, mode_str, standalone in _KEYWORD_MODE:
        if any(k.lower() in low for k in kws):
            return LearningMode(mode_str), mode_str, standalone
    return LearningMode(_DEFAULT_MODE), _DEFAULT_MODE, True


def _components(config: Config, skill_id: str) -> list[str]:
    names = {s["id"]: s["name"] or s["id"] for s in _skill_names(config)}
    rel = relations(config, skill_id)
    comp_ids = rel.get("composite_of") or []
    return [names.get(c, c) for c in comp_ids]


def _skill_names(config: Config) -> list[dict]:
    from app.knowledge import list_skills

    return list_skills(config)


def path_for(mode: LearningMode) -> list[StageSpec]:
    return list(MODE_PATHS.get(mode, MODE_PATHS[LearningMode.LIBRARY]))