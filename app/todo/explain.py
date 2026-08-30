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


def build_steps(config, name: str, skill_id: str | None = None, delta: int = 1) -> list[str]:
    """把一个技能任务拆成「每个环节做什么」的逐步清单（骨架级别）。

    已从「固定模板生成器」改为「兜底生成器」：先由 Skill Classification 判定该技能
    属于哪类学习对象（framework / mechanism / api / ...），再按对应学习模式给出骨架，
    避免 Checkpoint、LLM API、RAG 全部套同一套「概念→环境→API→项目→验收」模板。
    真正执行级细节由 ExecutionPlanRefiner（execution_steps）负责。
    """
    from app.agents.task_refinement import build_steps_fallback

    return build_steps_fallback(config, name, skill_id or name, delta)


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