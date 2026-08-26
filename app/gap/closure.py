"""前置关系闭包与拓扑排序（阶段 4，closure）。

requires 边约定与 seed_skill_graph 一致：source=前置技能, target=依赖该前置的技能。
即对技能 t，其前置集合 = edges 中所有 target==t 的 source。
"""
from __future__ import annotations

from collections import deque, defaultdict


def prereq_map(edges: list[tuple[str, str]]) -> dict[str, list[str]]:
    """dependent → [prereq...]（target → 命中 source 列表）。"""
    pm: dict[str, list[str]] = defaultdict(list)
    seen: set[tuple[str, str]] = set()
    for source, target in edges:
        if (source, target) in seen:
            continue
        seen.add((source, target))
        pm.setdefault(target, [])
        if source not in pm[target]:
            pm[target].append(source)
    return pm


def transitive_prereqs(edges: list[tuple[str, str]], seed: str) -> set[str]:
    """沿 requires 反向 BFS 求 seed 的传递前置闭包（不含 seed 自身）。"""
    pm = prereq_map(edges)
    visited: set[str] = set()
    stack = [seed]
    while stack:
        cur = stack.pop()
        for pre in pm.get(cur, ()):
            if pre not in visited:
                visited.add(pre)
                stack.append(pre)
    visited.discard(seed)
    return visited


def topo_sort(nodes: list[str], edges: list[tuple[str, str]]) -> list[str]:
    """对给定技能集合做拓扑排序：前置者先。

    仅考虑 source、target 都在 nodes 内的边；遇环时环内节点稳定去重追加到末尾，
    保证结果始终完整、有序。
    """
    node_set: set[str] = set(nodes)
    adj: dict[str, set[str]] = defaultdict(set)
    indeg = {n: 0 for n in node_set}
    for source, target in edges:
        if source in node_set and target in node_set:
            if target not in adj[source]:
                adj[source].add(target)
                indeg[target] += 1

    queue = deque(sorted((n for n, d in indeg.items() if d == 0)))
    ordered: list[str] = []
    while queue:
        u = queue.popleft()
        ordered.append(u)
        for v in sorted(adj[u]):
            indeg[v] -= 1
            if indeg[v] == 0:
                queue.append(v)

    # 环兜底：未排出的节点按字典序附在末尾
    remaining = sorted(n for n in node_set if n not in ordered)
    return ordered + remaining