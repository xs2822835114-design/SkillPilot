"""学习计划调度（阶段 5，scheduler）：拓扑序 + 周预算分桶 → phases（纯规则，可重复）。

依赖消费：阶段 4 的 SkillGapReport.recommended_sequence（已按前瞻拓扑有序）与
gaps[].required_level/current_level。顺序/分桶/时间估算全部规则计算，不依赖 LLM。
"""
from __future__ import annotations

import math

from app.gap import closure
from app.gap.schemas import SkillGapReport


def skill_deltas(report: SkillGapReport) -> dict[str, int]:
    """每技能等级差快照：gaps 用 required-current；其余（隐式前置）默认 1。"""
    deltas = {g.skill_id: max(0, g.required_level - g.current_level) for g in report.gaps}
    for sid in report.recommended_sequence:
        deltas.setdefault(sid, 1)
    return deltas


def depth_map(sequence: list[str], edges: list[tuple[str, str]]) -> dict[str, int]:
    """按 requires 前置关系求每技能的最长路径深度（拓扑有序序列下稳定）。

    深度相同⇒相互无前置依赖、可并行；深度更深⇒依赖更深技能，必须后置。
    """
    pm = closure.prereq_map(edges)  # target → [prereq...]
    depth: dict[str, int] = {}
    for node in sequence:
        pre_depths = [depth[p] for p in pm.get(node, ()) if p in depth]
        depth[node] = (max(pre_depths) + 1) if pre_depths else 0
    return depth


def estimate_hours(delta: int, min_h: float, max_h: float, hours_per_level: float) -> float:
    """按等级差估算任务小时：clamp(delta * per_level, min, max)，保留一位小数。"""
    raw = max(1, int(delta or 1)) * hours_per_level
    return round(min(max(raw, min_h), max_h), 1)


def _group_by_depth(sequence: list[str], edges: list[tuple[str, str]]) -> list[list[str]]:
    """把有序序列按拓扑深度分组为 phases（组内可并行，组间严格前置）。"""
    depth = depth_map(sequence, edges)
    buckets: dict[int, list[str]] = {}
    for sid in sequence:
        buckets.setdefault(depth[sid], []).append(sid)
    return [buckets[d] for d in sorted(buckets)]


def _merge_to_cap(groups: list[list[str]], cap: int) -> list[list[str]]:
    """合并相邻 depth 组以不超过 cap，且保持前置顺序（仅相邻合并，安全）。"""
    groups = [list(g) for g in groups]
    while len(groups) > cap:
        # 优先合并任务数最少的相邻对，减少过度耦合；都不足时合并末尾
        best = (0, len(groups[0]) + len(groups[1]))
        for i in range(len(groups) - 1):
            cost = len(groups[i]) + len(groups[i + 1])
            if cost < best[1]:
                best = (i, cost)
        i = best[0]
        merged = groups[i] + groups[i + 1]
        groups[i : i + 2] = [merged]
    return groups


def split_phases(
    report: SkillGapReport,
    edges: list[tuple[str, str]],
    phases_cap: int | None,
) -> list[list[str]]:
    """SkillGapReport.recommended_sequence → 有序 phase 分组（每组为 skill 列表）。"""
    seq = list(report.recommended_sequence)
    if not seq:
        return []
    groups = _group_by_depth(seq, edges)
    if phases_cap:
        groups = _merge_to_cap(groups, max(1, phases_cap))
    return groups


def compute_metrics(tasks: list, weekly_hours: int | None) -> dict:
    """汇总 metrics：total_hours / total_tasks / done_tasks / weeks_est。"""
    total_hours = round(sum(float(t.estimated_hours) for t in tasks), 1)
    total_tasks = len(tasks)
    done_tasks = sum(1 for t in tasks if t.status == "done")
    weeks_est = None
    if weekly_hours and weekly_hours > 0 and total_hours > 0:
        weeks_est = math.ceil(total_hours / weekly_hours)
    return {
        "total_hours": total_hours,
        "total_tasks": total_tasks,
        "done_tasks": done_tasks,
        "weeks_est": weeks_est,
    }