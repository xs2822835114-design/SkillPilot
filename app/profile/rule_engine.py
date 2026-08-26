"""等级与置信度规则（阶段 3）：纯规则、可重复，LLM 不参与给分。"""
from __future__ import annotations


def level_from_scores(theory: int, practice: int, practice_weight: float = 0.6) -> int:
    """theory/practice(0-100) → level(0-5)。

    公式：raw = (1-w)*theory + w*practice；level = floor(raw/20) 上限 5。
    """
    theory = max(0, min(100, int(theory or 0)))
    practice = max(0, min(100, int(practice or 0)))
    p = max(0.0, min(1.0, float(practice_weight)))
    raw = (1 - p) * theory + p * practice
    return min(5, int(raw // 20))


def merge_confidence(prev: float | None, incoming: float | None) -> float:
    """新旧置信度合并：merged = 0.4*prev + 0.6*incoming。"""
    prev = float(prev) if prev is not None else 0.0
    incoming = float(incoming) if incoming is not None else 0.0
    return round(0.4 * prev + 0.6 * incoming, 4)