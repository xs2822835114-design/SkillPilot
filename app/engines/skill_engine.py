"""技能等级估算引擎（方案第 11 节）：行为证据 → level/confidence/evidence。

纯规则、可重复、可单测，LLM 不参与给分——这是「Agent 负责理解，Engine 负责计算」
边界中 Engine 侧的核心：从用户自述的行为证据推导技能等级，而不是让 LLM 直接打分。
"""
from __future__ import annotations

from app.domain import UserSkill

# 显式否认（优先匹配，命中即等级 0）
_NEGATIVE = (
    "不会", "没学过", "没接触", "不了解", "没用过", "不懂", "没做过",
    "完全不会", "没怎么", "不清楚", "不会用", "从没",
)

# 行为证据关键词 → 等级（按等级的降序排列，取命中的最高等级）
_LEVEL_KEYWORDS: list[tuple[int, tuple[str, ...]]] = [
    (5, ("精通", "方法论", "沉淀", "复杂系统", "多年经验", "专家", "主导过", "优化过", "调优", "架构演进")),
    (4, ("独立设计", "系统设计", "架构", "独立完成", "从零搭建", "从零开发", "主导", "设计过", "整体架构", "独立负责")),
    (3, ("项目", "实战", "开发过", "做过", "搭建", "上线", "独立开发", "写过", "用过", "写项目", "落地", "接入了")),
    (2, ("脚本", "会用", "能写", "简单", "基础", "入门", "会一点", "用过一点", "练习", "写了点", "学过")),
    (1, ("听说过", "知道", "了解", "接触过", "认识", "看过", "学过一点", "懂一点", "知道是")),
]

_CONFIDENCE_BY_LEVEL = {5: 0.85, 4: 0.80, 3: 0.72, 2: 0.60, 1: 0.50, 0: 0.80}


def estimate_level(answer: str) -> tuple[int | None, float, list[str]]:
    """用户回答 → ``(level, confidence, evidence)``。

    - ``level``：0-5；``None`` 表示无法从现有证据判定（由下游视作 0 级缺口）。
    - ``confidence``：0-1，基于显式否认 > 高等级证据 > 低等级证据的确定性。
    - ``evidence``：命中的行为证据关键词（作为 UserSkill.evidence 存证）。
    """
    text = (answer or "").strip()
    if not text:
        return None, 0.0, []

    neg = [k for k in _NEGATIVE if k in text]
    if neg:
        return 0, _CONFIDENCE_BY_LEVEL[0], neg

    evidence: list[str] = []
    level = 0
    for lv, kws in _LEVEL_KEYWORDS:
        for k in kws:
            if k in text:
                evidence.append(k)
                level = max(level, lv)

    if not evidence:
        return None, 0.0, []

    conf = _CONFIDENCE_BY_LEVEL[level] + 0.05 * min(len(evidence) - 1, 4)
    conf = min(0.95, round(conf, 2))
    return level, conf, evidence


def to_user_skill(skill_id: str, skill_name: str, level: int | None, confidence: float, evidence: list[str]) -> UserSkill:
    """组装单条 UserSkill（领域契约）。"""
    return UserSkill(
        skill_id=skill_id,
        skill_name=skill_name,
        level=level,
        confidence=confidence,
        evidence=evidence,
    )