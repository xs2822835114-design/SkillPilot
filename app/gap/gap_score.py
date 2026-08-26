"""缺口评分规则（阶段 4，gap_score）：score / priority 纯规则、可重复，LLM 不参与。"""
from __future__ import annotations


def gap_score(required_level: int, current_level: int, weight: float, decay: float = 1.0) -> float:
    """计算单个缺口 score（0..1，可重复）。

    score = round( weight * (delta / 5.0) * decay, 3 )
    delta   = max(0, required_level - current_level)   # 缺失视为 0 级
    decay   = 缺失前置的降权系数（GAP_PREREQ_DECAY，默认 0.5），岗位直接缺口为 1.0。
    """
    delta = max(0, int(required_level) - int(current_level))
    w = max(0.0, min(1.0, float(weight)))
    d = max(0.0, min(1.0, float(decay)))
    return round(w * (delta / 5.0) * d, 3)


def priority(weight: float, delta: int) -> str:
    """由权重与等级差定优先级：核心缺失 P1 / 较重要 P2 / 其他 P3。"""
    w = float(weight)
    d = int(delta)
    if w >= 0.9 and d >= 2:
        return "P1"
    if w >= 0.7:
        return "P2"
    return "P3"


def coverage_rate(covered: int, total: int) -> float:
    if total <= 0:
        return 0.0
    return round(covered / total, 3)