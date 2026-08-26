"""规则评分（阶段 6，evaluation/scorer）：CheckResult[] → theory/practice/overall + 建议。

评分纯规则、可重复；区分理论（语法/结构/代码质量）与实践（可运行性/测试）。
LLM 不参与给分，仅 recommendations 可选润色。
"""
from __future__ import annotations

import logging
from typing import Any

from app.config import Config
from app.evaluation.schemas import EvidenceItem, SkillScore

logger = logging.getLogger(__name__)


def build_evidence(checks: list[dict[str, Any]], strict: bool) -> list[EvidenceItem]:
    return [EvidenceItem(type=c["type"], passed=bool(c["passed"]), message=c.get("message", "")) for c in checks]


def _literal_score(checks: list[dict[str, Any]], fail_keys: dict[str, int]) -> int:
    penalty = 0
    for c in checks:
        if not c["passed"]:
            penalty += fail_keys.get(c["type"], 0)
    return max(0, min(100, 100 - penalty))


def score(
    config: Config, skill_id: str, checks: list[dict[str, Any]]
) -> tuple[int, int, int, list[str]]:
    """返回 (theory, practice, overall, recommendations)。整体 clamp 0..100。"""
    empty = any(c["type"] == "empty" for c in checks)
    if empty:
        return 0, 0, 0, ["未收到有效代码，无法评分"]

    theory = _literal_score(checks, {
        "syntax": 50, "structure": 20, "lint": 15,
    })
    practice = _literal_score(checks, {
        "runnable": 45, "tests": 30, "syntax": 20,
    })
    w = config.eval_theory_weight
    overall = int(round(w * theory + (1 - w) * practice))

    recs = _recommendations(checks, skill_id)
    return theory, practice, overall, recs


def _recommendations(checks: list[dict[str, Any]], skill_id: str) -> list[str]:
    by = {c["type"]: c for c in checks}
    recs: list[str] = []
    if not by.get("syntax", {}).get("passed", True):
        recs.append("存在语法错误，请先修复后重新评估")
    if not by.get("runnable", {}).get("passed", True):
        recs.append("未发现可执行入口，建议补充 __main__ 或顶层调用")
    if by.get("tests", {}).get("passed", False) is False:
        recs.append(f"测试覆盖不足：建议为 {skill_id} 补充 2 个边界用例后再评估")
    if by.get("lint", {}).get("passed", True) is False:
        recs.append("存在未使用导入或 TODO 注释，建议清理后再提交")
    if not recs:
        recs.append("实践达到可执行、可测试标准，可结合功课做更高目标练习")
    return recs


def llm_polish_recommendations(recs: list[str], config: Config | None = None) -> list[str] | None:
    """可选：用 LLM 润色建议文案；失败返回 None 由模板兜底。"""
    try:
        from langchain_core.prompts import ChatPromptTemplate
        from langchain_openai import ChatOpenAI

        if config is None:
            from app.config import get_config

            config = get_config()
        if not config.eval_llm_enabled or not config.llm_enabled:
            return None
        llm = ChatOpenAI(
            model=config.llm_model, base_url=config.llm_base_url, api_key=config.llm_api_key, temperature=0.3
        )
        prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    "你是技能评估教练。把给定的改进建议改写为更具体、可执行的短句（每条 ≤30 字）。"
                    "逐行输出，不要编号。",
                ),
                ("human", "\n".join(recs)),
            ],
        )
        resp = (prompt | llm).invoke({})
        text = (resp.content if hasattr(resp, "content") else str(resp)).strip()
        lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
        return lines or None
    except Exception:  # noqa: BLE001
        logger.warning("Evaluation recommendations LLM 润色失败，走模板兜底", exc_info=True)
        return None


def build_skill_scores(skill_id: str, theory: int, practice: int) -> list[SkillScore]:
    return [SkillScore(skill_id=skill_id, theory=theory, practice=practice)]