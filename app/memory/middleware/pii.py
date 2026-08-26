"""阶段 7 PII 中间件（memory/middleware/pii）：写入记忆前的敏感信息脱敏。

正则覆盖常见敏感格式（邮箱/手机号/身份证/长数字）。`MEMORY_PII_ENABLED=false` 时原样返回。
仅做文本与结构字段的字段级脱敏，不做业务判断。
"""
from __future__ import annotations

import re

from app.config import Config

_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("email", re.compile(r"[\w.+\-]+@[\w\-]+(?:\.[\w\-]+)+")),
    ("phone", re.compile(r"(?<!\w)\+?\d[-\d ]{6,16}\d(?!\w)")),
    ("id_card", re.compile(r"(?<!\d)\d{17}[\dXx](?!\d)")),
]

_PLACEHOLDER = {t: f"[REDACTED:{t}]" for t, _ in _PATTERNS}


def scrub(config: Config, text: str) -> tuple[str, list[str]]:
    """返回 (脱敏文本, 命中类型列表)。未开启或文本为空则原样返回。"""
    if not getattr(config, "memory_pii_enabled", True) or not text:
        return text, []
    hit: list[str] = []
    out = text
    # 先掩长实身份证，再掩手机号，最后掩邮箱，避免嵌套误匹配
    for kind, pattern in reversed(_PATTERNS):
        if pattern.search(out):
            out = pattern.sub(_PLACEHOLDER[kind], out)
            hit.append(kind)
    return out, hit


def mask_payload(config: Config, payload: dict) -> dict:
    """对 payload 中的全部字符串字段做脱敏（原地返回新 dict）。"""
    return {k: (_mask_val(config, v)) for k, v in payload.items()}


def _mask_val(config: Config, v):
    if isinstance(v, str):
        return scrub(config, v)[0]
    if isinstance(v, dict):
        return {k: _mask_val(config, x) for k, x in v.items()}
    if isinstance(v, list):
        return [_mask_val(config, x) for x in v]
    return v