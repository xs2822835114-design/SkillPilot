"""TaskRefinementAgent（执行计划精炼）测试。

规则兜底路径为纯单元测试，始终运行（无 DB、无 LLM）。
"""
from __future__ import annotations

import pytest

from app.agents.task_refinement import (
    TaskRefinementAgent,
    get_skill_context,
    refine_learning_plan,
)
from app.config import Config
from app.domain.execution import TaskRefinementInput
from app.todo.schemas import LearningPlan, LearningPhase, LearningTask


@pytest.fixture()
def cfg():
    # llm_api_key 为空 → 走规则兜底，结果确定可断言
    return Config(env="test", database_url="", llm_api_key="")


def test_refine_rules_atomic_and_verifiable(cfg):
    agent = TaskRefinementAgent(cfg)
    out = agent.refine_task(
        TaskRefinementInput(
            task_id="PLAN_1-T01",
            skill_id="sqlalchemy",
            skill_name="SQLAlchemy",
            goal="成为 AI Agent 后端开发者",
            gap=3,
            estimated_hours=4,
            acceptance_criteria="理解并掌握核心概念",
            existing_steps=["建立概念", "环境准备", "核心用法"],
        )
    )
    # 拆出 5~7 个原子步骤，且每步都有可验证标准
    assert 5 <= len(out.execution_steps) <= 7
    for s in out.execution_steps:
        assert s.title.strip()
        assert s.verification.strip(), f"{s.step_id} 缺 verification"
        assert s.deliverable.strip(), f"{s.step_id} 缺 deliverable"
        assert 5 <= s.estimated_minutes <= 240
    # 总时长接近 estimated_hours 的合理区间（180~260 分钟）
    assert 120 <= out.total_estimated_minutes <= 320
    assert out.is_refined is True


def test_get_skill_context_from_graph(cfg):
    ctx = get_skill_context(cfg, "llm_api")
    assert ctx["skill_id"] == "llm_api"
    assert isinstance(ctx["prerequisites"], list)


def test_refine_learning_plan_fills_tasks(cfg):
    t1 = LearningTask(
        task_id="P-T01",
        skill_id="llm_api",
        title="学习并掌握 LLM API",
        estimated_hours=4,
        acceptance_criteria="掌握 LLM API",
        steps=["建立概念"],
    )
    plan = LearningPlan(
        plan_id="P",
        user_id="u1",
        goal="LLM 开发",
        phases=[LearningPhase(phase_id="P1", title="基础", order=1, skill_ids=["llm_api"], tasks=[t1])],
    )
    refine_learning_plan(cfg, plan)
    assert t1.is_refined is True
    assert len(t1.execution_steps) >= 5