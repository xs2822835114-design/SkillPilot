"""阶段 1：app/domain 领域契约单测（纯数据结构，不依赖 DB / LLM）。"""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.domain import (
    IntentResult,
    IntentType,
    JobRequirement,
    Role,
    SkillRequirement,
    TargetProfile,
    TechRequirement,
    UserSkill,
    UserSkillProfile,
)


def test_intent_type_values():
    assert IntentType.CHAT.value == "chat"
    assert IntentType.TECH_LEARNING.value == "tech_learning"
    assert IntentType.JOB_SEARCH.value == "job_search"


def test_intent_result_roundtrip():
    r = IntentResult(intent=IntentType.TECH_LEARNING, confidence=0.9, reason="想学技术")
    assert r.intent is IntentType.TECH_LEARNING
    # str Enum 支持按字符串构造
    r2 = IntentResult(intent="job_search")
    assert r2.intent is IntentType.JOB_SEARCH
    assert r.model_dump()["intent"] == "tech_learning"


def test_intent_result_confidence_bounds():
    with pytest.raises(ValidationError):
        IntentResult(intent=IntentType.CHAT, confidence=1.5)


def test_skill_requirement_defaults_and_bounds():
    s = SkillRequirement(skill_id="python", required_level=4, weight=0.9)
    assert s.skill_name == ""
    assert s.weight == 0.9
    with pytest.raises(ValidationError):
        SkillRequirement(skill_id="x", required_level=6)


def test_tech_requirement_example():
    t = TechRequirement(
        goal="学习 LangGraph",
        target_skills=["LangGraph"],
        related_skills=["LangChain", "Tool Calling", "RAG"],
        prerequisites=["Python", "LLM API"],
    )
    assert "LangGraph" in t.target_skills
    with pytest.raises(ValidationError):
        TechRequirement(goal="")


def test_job_requirement():
    j = JobRequirement(
        role_id="RC002",
        role_name="AI Agent 工程师",
        required_skills=[SkillRequirement(skill_id="langgraph", required_level=4)],
    )
    assert j.role_id == "RC002"
    assert j.required_skills[0].skill_id == "langgraph"


def test_role():
    r = Role(role_id="RC002", role_name="AI Agent 工程师", seniority="中级")
    assert r.role_name == "AI Agent 工程师"


def test_target_profile():
    p = TargetProfile(
        goal_type="job_search",
        goal_name="AI Agent 工程师",
        skills=[SkillRequirement(skill_id="python", required_level=4)],
    )
    assert p.goal_type == "job_search"
    assert len(p.skills) == 1


def test_user_skill_profile():
    u = UserSkillProfile(
        user_id="user_001",
        skills=[UserSkill(skill_id="python", level=3, confidence=0.9, evidence=["Flask 项目"])],
    )
    assert u.skills[0].level == 3
    assert u.last_updated is not None