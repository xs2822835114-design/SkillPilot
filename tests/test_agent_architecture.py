"""Agent 架构新增能力单测（阶段 3~8，覆盖意图路由 + 目标画像 + 后续闭环）。

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


# ---------------- 阶段 4：目标画像（tech / job → TargetProfile） ----------------
#
# 说明：目标画像构建成功后，编排会继续进入「技能访谈」（阶段 5），因此首轮以
# need_input（访谈追问）收尾，target_profile 仍随 artifacts 透出供前端展示。


def test_job_search_builds_target_profile(client):
    resp = _chat(client, "N_J2", "我想找 AI Agent 工程师岗位")
    data = resp.get_json()["data"]
    assert data["route"] == "job_search"
    # 目标画像已建立 → 进入技能访谈（首轮追问）
    assert data["workflow_status"] == "need_input"
    assert "skill_interview_agent" in data["steps"]
    art = data["artifacts"]
    assert art["intent"] == "job_search"
    profile = art["target_profile"]
    assert profile["goal_type"] == "job_search"
    assert profile["goal_name"] == "AI Agent 工程师"
    ids = {s["skill_id"] for s in profile["skills"]}
    assert "langgraph" in ids
    assert "python" in ids
    assert "llm_api" in ids


def test_tech_learning_builds_target_profile(client):
    resp = _chat(client, "N_T2", "我想学 LangGraph")
    data = resp.get_json()["data"]
    assert data["route"] == "tech_learning"
    # 目标画像已建立 → 进入技能访谈（首轮追问）
    assert data["workflow_status"] == "need_input"
    assert "skill_interview_agent" in data["steps"]
    profile = data["artifacts"]["target_profile"]
    assert profile["goal_type"] == "tech_learning"
    assert profile["goal_name"] == "LangGraph"
    ids = {s["skill_id"] for s in profile["skills"]}
    assert "langgraph" in ids       # 目标技能
    assert "python" in ids          # 前置
    assert "llm_api" in ids         # 前置
    assert "langchain" in ids       # 前置


# ---------------- 阶段 4（单元）：确定性展开 ----------------


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


# ---------------- 阶段 5/6：访谈 → 缺口 完整闭环 ----------------


def _finish_interview(client, tid: str, first_data: dict, answers_by_skill: dict, default: str = "我写过项目") -> dict:
    """逐轮回答访谈直到 done：每轮从 artifacts.interview_question 取当前 skill_id，
    用映射好的答案（缺省用 default）作答，返回最终 data。

    题量已由固定 5 改为「按目标画像询问全部相关技能」，故这里用轮询而非硬编码长度。
    """
    data = first_data
    for _ in range(24):
        if data.get("workflow_status") == "done":
            return data
        q = (data.get("artifacts") or {}).get("interview_question") or {}
        sid = q.get("skill_id") or ""
        data = _chat(client, tid, answers_by_skill.get(sid, default)).get_json()["data"]
    raise AssertionError("访谈未在限定轮次内结束")


def test_tech_learning_closed_loop(client):
    """目标画像 → 多轮访谈 → GapEngine：最终 done 并产出 deficit/learning_path/learning_plan。"""
    tid = "N_LOOP_TECH"
    first = _chat(client, tid, "我想学 LangGraph").get_json()["data"]
    assert first["workflow_status"] == "need_input"
    final = _finish_interview(
        client,
        tid,
        first,
        {
            "langgraph": "没怎么接触过",              # 目标技能 → 0，必然进入缺口
            "python": "我写过 Flask 项目和爬虫",      # Python → 3
            "llm_api": "用 DeepSeek API 做过聊天机器人",  # LLM API → 3
        },
    )
    assert final["workflow_status"] == "done"
    assert "gap_engine" in final["steps"]
    art = final["artifacts"]
    assert art["intent"] == "tech_learning"
    assert art["skill_gaps"]
    assert art["learning_path"]
    assert art["learning_plan"]
    # 学习计划按学习路径排序，且目标技能 LangGraph 一定在缺口里
    gap_ids = [g["skill_id"] for g in art["skill_gaps"]]
    assert "langgraph" in gap_ids


def test_job_search_closed_loop(client):
    """岗位求职闭环：访谈完成后 → 缺口 + 岗位匹配（recommended_roles）。"""
    tid = "N_LOOP_JOB"
    first = _chat(client, tid, "我想找 AI Agent 工程师岗位").get_json()["data"]
    assert first["workflow_status"] == "need_input"
    final = _finish_interview(client, tid, first, {"langgraph": "没怎么接触过"})
    assert final["workflow_status"] == "done"
    art = final["artifacts"]
    assert art["intent"] == "job_search"
    assert art["skill_gaps"]
    assert art["recommended_roles"]
    assert art["target_profile"]["goal_name"] == "AI Agent 工程师"