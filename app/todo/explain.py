"""任务描述 / 资源 / 验收模板与可选 LLM 润色（阶段 5，explain）。

顺序/分桶/验收结构默认规则生成，不依赖 LLM；仅 tasks 描述、plan goal 等文案
可由 LLM 润色，失败走模板兜底。资源推荐已去除（RAG 已精简移除）。
"""
from __future__ import annotations

import logging

from app.config import Config
from app.todo.schemas import LearningResource

logger = logging.getLogger(__name__)


def build_task_title(name: str, delta: int, priority: str) -> str:
    return f"学习并掌握 {name}"


def build_acceptance(name: str, delta: int) -> str:
    return f"理解并掌握 {name} 的核心概念，能独立完成一个可运行的示例并讲清使用场景。"


def build_steps(name: str, delta: int) -> list[str]:
    """把一个技能任务拆成「每个环节做什么」的逐步清单。

    环节随等级差（delta）逐级加深：delta 越大越深入（项目实战/系统设计），
    保证同一技能在不同缺口下给出不同粒度的动作，而不是千篇一律的模板。
    """
    d = max(1, int(delta or 1))
    steps = [
        f"建立概念：通读 {name} 官方 Overview 与 Getting Started，弄清它解决什么问题、与相邻技术的边界",
        f"环境准备：搭好 {name} 的本地开发/运行环境，跑通官方最小示例并理解每一步",
        f"核心用法：系统练习 {name} 的核心 API 与典型用法，写 3～5 个可独立运行的小练习",
    ]
    if d >= 2:
        steps.append(f"组合实践：把 {name} 与相关技术串联，落地一个贴近真实场景的小项目")
    if d >= 3:
        steps.append(f"进阶挑战：深入 {name} 原理/源码或高阶特性，独立设计并实现一个完整可用的系统")
    steps.append(f"验收复盘：对照验收标准自查，产出一篇学习笔记或可复现工程，沉淀为可复用经验")
    return steps


def build_goal(role_name: str) -> str:
    return f"{role_name} 能力达成计划" if role_name else "自定义目标能力达成计划"


def build_phase_title(skills, names: dict[str, str]) -> str:
    shown = "、".join(names.get(s, s) for s in skills)
    return f"阶段基础：{shown}" if len(skills) > 1 else f"{names.get(skills[0], skills[0])}"


# ---------------- 学习资源（已去除 RAG，资源留空，不阻塞规划） ----------------

def resources_for_skill(config: Config, skill_id: str, name: str) -> list[LearningResource]:
    """RAG 已按需求移除，返回空资源列表（不阻塞规划）。"""
    return []


# ---------------- LLM 润色（兜底） ----------------

def llm_polish_goal(goal: str, style: str | None) -> str | None:
    """用 LLM 润色 plan 的 goal 文案；失败返回 None 由模板兜底。"""
    try:
        from langchain_core.prompts import ChatPromptTemplate
        from langchain_openai import ChatOpenAI

        from app.config import get_config

        cfg = get_config()
        if not cfg.plan_llm_enabled or not cfg.llm_enabled:
            return None
        llm = ChatOpenAI(
            model=cfg.llm_model,
            base_url=cfg.llm_base_url,
            api_key=cfg.llm_api_key,
            temperature=0.3,
        )
        prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    "你是一名技术成长规划师。给出一句话（≤20 字）的学习计划目标文案。只输出目标文本。",
                ),
                ("human", "基础目标：{goal}；学习偏好：{style}"),
            ],
        )
        resp = (prompt | llm).invoke({"goal": goal, "style": style or "无"})
        text = (resp.content if hasattr(resp, "content") else str(resp)).strip()
        return text or None
    except Exception:  # noqa: BLE001
        logger.warning("Plan goal LLM 润色失败，走模板兜底", exc_info=True)
        return None