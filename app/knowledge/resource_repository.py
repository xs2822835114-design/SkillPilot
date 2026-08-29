"""学习资源 repository：按技能匹配学习资料（方案第 19 节）。

数据源：knowledge_sources JSON（未入库，直接读文件）。
"""
from __future__ import annotations

from app.config import Config
from app.knowledge import _json_source


def resources_for(config: Config | None, skill_name: str, limit: int = 5) -> list[dict]:
    """按技能名匹配学习资源（technology/title/category/description 任一命中）。

    返回原始 source dict 列表，最多 ``limit`` 条。
    """
    q = _json_source.slug(skill_name)
    q_cn = str(skill_name or "").strip().lower()
    hits: list[dict] = []
    for s in _json_source.load_sources():
        tech = [_json_source.slug(t) for t in (s.get("technology", []) or [])]
        title = (s.get("title", "") or "").lower()
        desc = (s.get("description", "") or "").lower()
        cat = (s.get("category", "") or "").lower()
        if not q:
            continue
        if q in tech or q_cn in title or q in title or q_cn in desc or q_cn in cat:
            hits.append(s)
        if len(hits) >= limit:
            break
    return hits