"""推荐引擎（方案第 15、16 节）：学习路径排序。

确定性、可重复：学习路径由技能图谱的 requires 拓扑排序得到。
"""
from __future__ import annotations

from app.config import Config
from app.gap import closure
from app.knowledge import _json_source


def _requires_edges() -> list[tuple[str, str]]:
    g = _json_source.load_graph()
    return [(s, t) for s, t, rel in g["edges"] if rel == "requires"]


def build_learning_path(config: Config, gap_skill_ids: list[str]) -> list[str]:
    """缺口技能 → 学习路径（前置者先，确定性拓扑排序）。

    只对传入的缺口技能集合排序，保证前置技能排在其依赖技能之前。
    """
    ids = list(dict.fromkeys(gap_skill_ids))
    return closure.topo_sort(ids, _requires_edges())