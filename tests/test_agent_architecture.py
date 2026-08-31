"""Agent 架构单测（阶段 3~4：意图路由 + 目标画像）。

访谈、缺口分析下线后，原「目标画像→访谈→缺口」闭环用例已随相关模块移除，
此处仅保留仍被学习计划生成复用：意图路由与确定性目标画像展开。
约定：均基于内存 checkpointer（无 DB / 无 LLM），保证确定性、可在 CI 始终运行。
"""
from __future__ import annotations

import pytest

from app.config import Config


@pytest.fixture()
def cfg():
    return Config(env="test", database_url="", llm_api_key="", checkpointer_backend="memory")


def _chat(client, thread_id: str, message: str, **overrides):
    body = {"user_id": "U10001", "thread_id": thread_id, "message": message, **overrides}
    return client.post("/api/v1/chat", json=body)


# ---------------- 阶段 3：意图路由（三意图 + 快捷路径） ----------------


def test_route_job_search(client):
    resp = _chat(client, "N_J1", "我想找 AI Agent 工程师岗位")
    assert resp.status_code == 200
    data = resp.get_json()["data"]
    assert data["route"] == "job_search"


def test_route_tech_learning(client):
    resp = _chat(client, "N_T1", "我想学 LangGraph")
    assert resp.status_code == 200
    data = resp.get_json()["data"]
    assert data["route"] == "tech_learning"


def test_route_plan_generation_still_works(client):
    resp = _chat(client, "N_P1", "帮我生成学习计划")
    assert resp.status_code == 200
    assert resp.get_json()["data"]["route"] == "plan_generation"


def test_route_chat_unchanged(client):
    resp = _chat(client, "N_C1", "你好，今天天气怎么样")
    assert resp.status_code == 200
    assert resp.get_json()["data"]["route"] == "chat"


# ---------------- 阶段 4（单元）：确定性目标画像展开 ----------------


def test_build_tech_target_direct(cfg):
    from app.agents.target_profile import build_tech_target

    target = build_tech_target(cfg, [{"skill_id": "langgraph", "skill_name": "LangGraph"}])
    assert target.goal_name == "LangGraph"
    target_skills = [s for s in target.skills if s.source == "target"]
    assert len(target_skills) == 1
    assert target_skills[0].skill_id == "langgraph"
    assert target_skills[0].required_level == 3
    prereq_ids = {s.skill_id for s in target.skills if s.source == "prerequisite"}
    assert {"python", "llm_api", "langchain"} <= prereq_ids


def test_build_tech_target_expands_composite_of(cfg):
    """方案第 5.2 节：composite_of 子能力也展开进目标画像（source=composite）。"""
    from app.agents.target_profile import build_tech_target

    target = build_tech_target(cfg, [{"skill_id": "langgraph", "skill_name": "LangGraph"}])
    composite = {s.skill_id: s for s in target.skills if s.source == "composite"}
    assert {"state_management", "checkpoint"} <= set(composite)
    # 子能力是「掌握组合即需具备的分部」，权重介于前置与关联之间
    weights = [s.weight for s in composite.values()]
    assert all(w == 0.6 for w in weights)
    # 排序稳定：target 在前，随后是前置(0.7) > 子能力(0.6) > 关联(0.3)
    sources = [s.source for s in target.skills]
    assert sources.index("composite") > max(sources.index("target"), sources.index("prerequisite"))
    assert sources.index("related") > sources.index("composite")


def test_build_job_target_direct(cfg):
    from app.agents.target_profile import build_job_target

    target = build_job_target(cfg, "RC002")
    assert target is not None
    assert target.goal_name == "AI Agent 工程师"
    assert target.goal_type == "job_search"
    levels = {s.skill_id: s.required_level for s in target.skills}
    assert levels["langgraph"] == 4
    assert build_job_target(cfg, "NOPE") is None