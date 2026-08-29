"""Engine 层单元测试（方案第 11~15 节）：证据→等级、缺口计算、学习路径、岗位匹配。

全部基于内存知识库（无 DB / 无 LLM），确定性、可在 CI 始终运行。
"""
from __future__ import annotations

import pytest

from app.config import Config
from app.domain import SkillRequirement, TargetProfile, UserSkill, UserSkillProfile


@pytest.fixture()
def cfg():
    return Config(env="test", database_url="", llm_api_key="", checkpointer_backend="memory")


# ---------------- 技能等级估算（skill_engine） ----------------


def test_estimate_level_negative(cfg):
    from app.engines import estimate_level

    level, conf, evidence = estimate_level("我没学过 Python，完全不会")
    assert level == 0
    assert conf >= 0.7
    assert any("没学过" in e or "完全不会" in e for e in evidence)


def test_estimate_level_project(cfg):
    from app.engines import estimate_level

    level, conf, evidence = estimate_level("我写过几个 Flask 项目，也做过爬虫")
    assert level >= 3
    assert conf >= 0.7


def test_estimate_level_architecture(cfg):
    from app.engines import estimate_level

    level, _, _ = estimate_level("能独立设计项目架构，主导过系统设计")
    assert level >= 4


def test_estimate_level_unknown(cfg):
    from app.engines import estimate_level

    level, conf, evidence = estimate_level("还行吧，一般般")
    assert level is None
    assert conf == 0.0
    assert evidence == []


# ---------------- 缺口引擎（gap_engine） ----------------


def test_compute_gaps_basic(cfg):
    from app.engines import compute_gaps

    target = TargetProfile(
        goal_type="tech_learning",
        goal_name="LangGraph",
        skills=[
            SkillRequirement(skill_id="python", skill_name="Python", required_level=3, weight=1.0, source="target"),
            SkillRequirement(skill_id="langgraph", skill_name="LangGraph", required_level=4, weight=1.0, source="target"),
        ],
    )
    user = UserSkillProfile(
        user_id="U1",
        skills=[UserSkill(skill_id="python", skill_name="Python", level=2, confidence=0.7)],
    )
    gaps = compute_gaps(cfg, target, user)
    by_id = {g.skill_id: g for g in gaps}
    assert "python" in by_id and "langgraph" in by_id
    assert by_id["python"].gap == 1
    assert by_id["langgraph"].gap == 4       # 未访谈 → 0 级，缺口 4
    assert by_id["langgraph"].current_level == 0


def test_compute_gaps_skips_covered(cfg):
    from app.engines import compute_gaps

    target = TargetProfile(
        goal_type="tech_learning",
        goal_name="Python",
        skills=[SkillRequirement(skill_id="python", skill_name="Python", required_level=3, weight=1.0, source="target")],
    )
    user = UserSkillProfile(
        user_id="U1",
        skills=[UserSkill(skill_id="python", skill_name="Python", level=4, confidence=0.8)],
    )
    assert compute_gaps(cfg, target, user) == []


# ---------------- 学习路径（recommendation_engine） ----------------


def test_build_learning_path_topological(cfg):
    from app.engines import build_learning_path

    path = build_learning_path(cfg, ["langgraph", "python", "langchain", "llm_api"])
    # 前置者先：python/llm_api 先于 langchain，langchain 先于 langgraph
    assert path.index("python") < path.index("langgraph")
    assert path.index("llm_api") < path.index("langchain")
    assert path.index("langchain") < path.index("langgraph")


def test_build_learning_plan_with_resources(cfg):
    from app.engines import build_learning_plan, compute_gaps

    target = TargetProfile(
        goal_type="tech_learning",
        goal_name="Python",
        skills=[SkillRequirement(skill_id="python", skill_name="Python", required_level=3, weight=1.0, source="target")],
    )
    user = UserSkillProfile(user_id="U1", skills=[])
    gaps = compute_gaps(cfg, target, user)
    plan = build_learning_plan(cfg, gaps, ["python"])
    assert len(plan) == 1
    assert plan[0]["skill_id"] == "python"
    assert plan[0]["gap"] == 3
    # 学习资源知识库能命中 Python 资源
    assert plan[0]["resources"]
    assert all(set(r) >= {"title", "url", "type", "category"} for r in plan[0]["resources"])


# ---------------- 岗位匹配（recommendation_engine） ----------------


def test_recommend_roles_ranked(cfg):
    from app.engines import recommend_roles

    user = UserSkillProfile(user_id="U1", skills=[])
    roles = recommend_roles(cfg, user, limit=5)
    assert roles
    assert all(set(r) >= {"role_id", "role_name", "coverage", "gap_count"} for r in roles)
    assert roles[0]["coverage"] == 0.0


def test_recommend_roles_prefers_matching(cfg):
    from app.engines import recommend_roles

    # 已覆盖 AI Agent 工程师的核心技能 → 它应排名靠前
    user = UserSkillProfile(
        user_id="U1",
        skills=[
            UserSkill(skill_id="langgraph", skill_name="LangGraph", level=4),
            UserSkill(skill_id="llm_api", skill_name="LLM API", level=4),
            UserSkill(skill_id="python", skill_name="Python", level=4),
        ],
    )
    roles = recommend_roles(cfg, user, limit=50)
    ai_agent = next((r for r in roles if r["role_id"] == "RC002"), None)
    assert ai_agent is not None
    assert ai_agent["coverage"] > 0