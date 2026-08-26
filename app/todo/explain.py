"""任务描述 / 资源 / 验收模板与可选 LLM 润色（阶段 5，explain）。

顺序/分桶/验收结构默认规则生成，不依赖 LLM；仅 tasks 描述、plan goal 等文案
可由 LLM 润色，失败走模板兜底。资源推荐来自 RAG（best-effort）。
"""
from __future__ import annotations

import logging

from app.config import Config
from app.todo.schemas import LearningResource

logger = logging.getLogger(__name__)


def build_task_title(name: str, delta: int, priority: str) -> str:
    if delta >= 3:
        return f"系统学习并上手 {name}（缺口较大，优先级 {priority}）"
    return f"补齐 {name} 基础（等级差 {max(1, delta)} 级）"


def build_acceptance(name: str, delta: int) -> str:
    if delta >= 3:
        return (
            f"能独立完成 {name} 相关的小型练习；给出可运行的示例并用自己的话解释核心概念，"
            f"作为阶段 6 实践任务的前提。"
        )
    return f"理解并应用 {name} 的核心概念，完成 1 个可运行的示例，能讲清使用场景。"


def build_goal(role_name: str) -> str:
    return f"{role_name} 能力达成计划" if role_name else "自定义目标能力达成计划"


def build_phase_title(skills, names: dict[str, str]) -> str:
    shown = "、".join(names.get(s, s) for s in skills)
    return f"阶段基础：{shown}" if len(skills) > 1 else f"{names.get(skills[0], skills[0])}"


# ---------------- RAG 资源（best-effort） ----------------

def resources_for_skill(config: Config, skill_id: str, name: str) -> list[LearningResource]:
    """按技能检索 RAG 资料作为推荐资源；失败/不可用则返回空列表（不阻塞规划）。"""
    if not name:
        return []
    try:
        if not config.database_url or not config.embedding_enabled:
            return []
        from app.rag.schemas import RagSearchRequest
        from app.rag.service import search

        resp = search(
            config,
            RagSearchRequest(
                query=f"{name} 学习资料 入门",
                top_k=2,
            ),
        )
        out: list[LearningResource] = []
        for it in resp.results:
            out.append(
                LearningResource(
                    title=it.title or it.source or (name + "资料"),
                    url=it.url or None,
                    source=it.source or None,
                    chunk_id=it.chunk_id,
                )
            )
        return out
    except Exception:  # noqa: BLE001
        logger.warning("RAG 资源推荐不可用，跳过（skill=%s）", skill_id)
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