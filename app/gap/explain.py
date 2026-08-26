"""解释与建议生成（阶段 4，explain）：reason 模板默认不依赖 LLM；suggestions 可选 LLM 润色。"""
from __future__ import annotations

import logging

from app.gap.schemas import SkillGapReport

logger = logging.getLogger(__name__)


def build_reason(name: str, required_level: int, current_level: int, weight: float, prereq_names: list[str] | None = None) -> str:
    """生成单条缺口的可读 reason（规则模板，非 LLM）。"""
    delta = max(0, int(required_level) - int(current_level))
    level_desc = "专家级" if required_level >= 5 else f"level {required_level}"
    parts = [
        f"{name}：岗位要求 {level_desc}，当前 level {current_level}，等级差 {delta} 级",
        f"（weight {round(float(weight), 2)}）",
    ]
    if delta == 0:
        parts = [f"{name}：已达到要求的 level {required_level}（weight {round(float(weight), 2)}）"]
    if prereq_names:
        parts.append(f"需先完成前置：{', '.join(prereq_names)}")
    return "，".join(parts)


def build_suggestions(report: SkillGapReport) -> str:
    """模板兜底建议：按 recommended_sequence 逐层推进（非 LLM）。"""
    if not report.recommended_sequence:
        return "当前画像已覆盖目标岗位的全部要求技能，无缺口。"
    seq = " → ".join(report.recommended_sequence)
    return (
        f"目标岗位「{report.target_role}」存在 {report.coverage.gap_total} 项缺口，"
        f"覆盖率 {report.coverage.coverage_rate:.1%}。建议按依赖顺序逐层补齐：{seq}。"
        f"优先处理 P1 核心技能（权重高且缺失较多）。"
    )


def llm_polish_suggestions(report: SkillGapReport) -> str | None:
    """用 LLM 润色 suggestions；失败或不可用返回 None（由调用方走模板兜底）。"""
    try:
        from langchain_core.prompts import ChatPromptTemplate
        from langchain_openai import ChatOpenAI

        from app.config import get_config

        cfg = get_config()
        if not cfg.gap_llm_enabled or not cfg.llm_enabled:
            return None
        gap_names = [f"{g.name}({g.priority})" for g in report.gaps]
        seq = " → ".join(report.recommended_sequence or [])
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
                    "你是一名技术成长顾问。根据用户的岗位缺口给出 2-4 句中文学习建议，"
                    "聚焦顺序、优先级与可执行动作。只输出建议文本，不要编号列表。",
                ),
                (
                    "human",
                    "岗位：{role}；缺口：{gaps}；推荐顺序：{seq}",
                ),
            ]
        )
        chain = prompt | llm
        resp = chain.invoke(
            {"role": report.target_role, "gaps": "、".join(gap_names), "seq": seq}
        )
        text = (resp.content if hasattr(resp, "content") else str(resp)).strip()
        return text or None
    except Exception:  # noqa: BLE001
        logger.warning("Gap suggestions LLM 润色失败，走模板兜底", exc_info=True)
        return None