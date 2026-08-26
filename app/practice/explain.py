"""实践交付物/指引文案模板 + LLM 润色兜底（阶段 6，practice/explain）。"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def build_guide(skill_name: str, acceptance: str, level_target: int) -> str:
    loop = "完成后请反思：哪些概念从'看得懂'变为'用得出来'"
    practice = "" if level_target < 4 else "；需包含至少一条边界/异常处理的实现"
    return (
        f"针对「{skill_name}」实践：交付物围绕 {acceptance} 展开{practice}。"
        f"{loop}。"
    )


def llm_polish_guide(guide: str, config=None) -> str | None:
    """用 LLM 润色实践指引文案；失败返回 None 由模板兜底。"""
    try:
        if config is None:
            from app.config import get_config

            config = get_config()
        from langchain_core.prompts import ChatPromptTemplate
        from langchain_openai import ChatOpenAI

        if not config.practice_llm_enabled or not config.llm_enabled:
            return None
        llm = ChatOpenAI(
            model=config.llm_model, base_url=config.llm_base_url, api_key=config.llm_api_key, temperature=0.3
        )
        prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    "你是技能实践教练。把给定实践指引扩写成一段可执行的说明（≤120 字），"
                    "包含交付物与验收要点。只输出扩写文本。",
                ),
                ("human", "{guide}"),
            ],
        )
        resp = (prompt | llm).invoke({"guide": guide})
        text = (resp.content if hasattr(resp, "content") else str(resp)).strip()
        return text or None
    except Exception:  # noqa: BLE001
        logger.warning("Practice guide LLM 润色失败，走模板兜底", exc_info=True)
        return None