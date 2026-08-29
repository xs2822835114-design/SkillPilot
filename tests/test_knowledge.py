"""阶段 2：app/knowledge 知识层单测（不依赖 DB，走 JSON 降级路径）。"""
from __future__ import annotations

import pytest

from app.config import Config
from app.knowledge import (
    list_skills,
    list_roles,
    find_role,
    get_role,
    prerequisites,
    relations,
    resolve_skill,
    resources_for,
)
from app.knowledge import _json_source


@pytest.fixture()
def cfg():
    return Config(env="test", database_url="", llm_api_key="", checkpointer_backend="memory")


def test_slug_known_values():
    assert _json_source.slug("LangGraph") == "langgraph"
    assert _json_source.slug("Python") == "python"
    # 斜杠后不消费字母 s（历史 bug 回归）
    assert _json_source.slug("Java/Scala") == "java_scala"
    assert _json_source.slug("Node/Graph 编排") == "node_graph_编排"


def test_load_graph_has_core_skills():
    g = _json_source.load_graph()
    assert "langgraph" in g["nodes"]
    assert g["nodes"]["langgraph"]["domain"] == "AI"
    assert len(g["edges"]) > 0


def test_list_skills(cfg):
    skills = list_skills(cfg)
    ids = {s["id"] for s in skills}
    assert "langgraph" in ids
    assert "python" in ids


def test_relations_and_prerequisites(cfg):
    rel = relations(cfg, "langgraph")
    # langgraph requires：Python、LLM API、LangChain
    assert "langchain" in rel["requires"]
    assert "python" in rel["requires"]
    assert "llm_api" in rel["requires"]
    # 前置去重有序
    pres = prerequisites(cfg, "langgraph")
    assert "python" in pres
    assert len(pres) == len(set(pres))


def test_resolve_skill(cfg):
    node = resolve_skill(cfg, "LangGraph")
    assert node is not None
    assert node["id"] == "langgraph"
    assert node["domain"] == "AI"
    assert resolve_skill(cfg, "不存在的技能XYZ") is None


def test_list_roles(cfg):
    roles = list_roles(cfg)
    assert len(roles) > 0
    ids = {r.role_id for r in roles}
    assert "RC002" in ids


def test_get_role(cfg):
    role = get_role(cfg, "RC002")
    assert role is not None
    assert role.role_name == "AI Agent 工程师"
    skills = {s.skill_id: s for s in role.required_skills}
    assert "langgraph" in skills
    assert skills["langgraph"].required_level == 4
    assert get_role(cfg, "NOPE") is None


def test_find_role(cfg):
    role = find_role(cfg, "AI Agent")
    assert role is not None
    assert role.role_id == "RC002"
    assert find_role(cfg, "不存在的岗位XYZ") is None


def test_resources_for(cfg):
    hits = resources_for(cfg, "Python", limit=5)
    assert len(hits) > 0
    assert any("python" in (h.get("title") or "").lower() for h in hits)