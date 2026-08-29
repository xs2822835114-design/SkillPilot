"""阶段 5 学习规划 / Todo 测试：TC-P1~P10。

规则类用例（scheduler 分桶/时间/metrics）为纯单元测试，始终运行；
集成用例依赖种子数据与 DATABASE_URL，未配置则跳过并自动 seed 技能图/画像。
"""
from __future__ import annotations

import os
import uuid

import pytest

from app.todo import scheduler


# ---------------- 纯规则用例（不依赖 DB） ----------------

U = lambda: "tu_p_" + uuid.uuid4().hex[:10]  # noqa: E731


def _edges():
    # requires：source=前置, target=技能
    return [
        ("python", "llm_api"),
        ("llm_api", "langchain"),
        ("python", "langchain"),
        ("langchain", "langgraph"),
    ]


def test_scheduler_depth_and_split():
    seq = ["python", "llm_api", "langchain", "langgraph"]
    depth = scheduler.depth_map(seq, _edges())
    assert depth["python"] == 0
    assert depth["llm_api"] == 1
    assert depth["langchain"] == 2
    assert depth["langgraph"] == 3
    groups = scheduler.split_phases(_ReportLike(seq), _edges(), None)
    assert groups == [["python"], ["llm_api"], ["langchain"], ["langgraph"]]


def test_scheduler_cap_merges_consecutive():
    seq = ["python", "llm_api", "langchain", "langgraph"]
    groups = scheduler.split_phases(_ReportLike(seq), _edges(), 2)
    assert len(groups) == 2
    # 顺序（含前置关系）不被打乱
    flat = [s for g in groups for s in g]
    assert flat == seq


def test_scheduler_estimate_hours_clamp():
    assert scheduler.estimate_hours(3, 2, 12, 3) == pytest.approx(9.0)
    assert scheduler.estimate_hours(6, 2, 12, 3) == pytest.approx(12.0)  # clamp max
    assert scheduler.estimate_hours(1, 2, 12, 3) == pytest.approx(3.0)
    assert scheduler.estimate_hours(0, 2, 12, 3) == pytest.approx(3.0)  # 至少 1 级


def test_scheduler_metrics_empty():
    assert scheduler.compute_metrics([], 8)["total_tasks"] == 0
    assert scheduler.compute_metrics([], 8)["weeks_est"] is None


def _ReportLike(seq, gaps=None):
    from app.gap.schemas import SkillGapReport

    return skill_report(seq, gaps or [])


def skill_report(seq, gaps):
    from app.gap.schemas import GapItem, SkillGapReport

    return SkillGapReport(
        user_id="u",
        target_role_id="RC002",
        target_role="AI Agent 工程师",
        recommended_sequence=seq,
        gaps=[GapItem(skill_id=s, required_level=4, current_level=0, score=0.8, priority="P1") for s in gaps],
    )


# ---------------- 集成用例（依赖真实 DB） ----------------

def _cfg_db():
    from app.config import get_config

    if not get_config().database_url:
        pytest.skip("DATABASE_URL 未配置，跳过 DB 集成用例")
    return get_config()


def _ensure_seed(cfg):
    from app.persistence import db as pgdb

    with pgdb.connect(cfg) as c:
        n = c.execute("SELECT count(*) FROM skill_nodes").fetchone()[0]
    if n == 0:
        from scripts.seed_skill_graph import run as seed_graph

        seed_graph()
    with pgdb.connect(cfg) as c:
        has_spring = c.execute("SELECT 1 FROM skills WHERE id='spring_boot'").fetchone()
    if not has_spring:
        from scripts.seed_skills import run as seed_skills

        seed_skills()


def _clean(conn, user_id):
    conn.execute(
        "DELETE FROM learning_plans WHERE user_id = %s", (user_id,)
    )


@pytest.fixture()
def db():
    cfg = _cfg_db()
    _ensure_seed(cfg)
    from app.persistence import db as pgdb

    user = U()
    with pgdb.connect(cfg) as conn:
        _clean(conn, user)
    yield cfg, user
    with pgdb.connect(cfg) as conn:
        _clean(conn, user)


@pytest.fixture()
def db_client():
    cfg = _cfg_db()
    _ensure_seed(cfg)
    from app import create_app
    from app.config import Config

    test_cfg = Config(
        env="test",
        database_url=cfg.database_url,
        llm_api_key="",
        checkpointer_backend="memory",
        embedding_provider="off",
    )
    flask_app = create_app(test_cfg)
    flask_app.config["TESTING"] = True
    return flask_app.test_client()


def _generate(cfg, user, offline=True, req_overrides=None):
    cfg.plan_llm_enabled = not offline
    from app.todo.schemas import PlanRequest

    req = PlanRequest(user_id=user, target_roles=["RC002"])
    if req_overrides:
        req = req.model_copy(update=req_overrides)
    from app.todo import planner

    return planner.generate(cfg, req)


def _phase_pos(plan):
    return {t.skill_id: phase.order for phase in plan.phases for t in phase.tasks if t.skill_id}


# TC-P1 计划符合前置关系
def test_tc_p1_prereq_order(db):
    cfg, user = db
    plan = _generate(cfg, user)
    assert plan.phases
    from app.gap import graph_store

    edges = graph_store.load_requires_edges(cfg)
    from app.gap import closure

    pos = _phase_pos(plan)
    pm = closure.prereq_map(edges)
    for skill, ph in pos.items():
        for pre in pm.get(skill, ()):
            if pre in pos:
                assert pos[pre] <= ph, f"{pre} 应早于或等于 {skill} 的 phase"


# TC-P2 字段齐全
def test_tc_p2_fields_complete(db):
    cfg, user = db
    plan = _generate(cfg, user)
    seen = 0
    for phase in plan.phases:
        for t in phase.tasks:
            seen += 1
            assert t.title.strip()
            assert t.estimated_hours > 0
            assert t.acceptance_criteria.strip()
            assert isinstance(t.resources, list)
            assert t.steps, f"{t.skill_id} 缺少学习环节步骤"
    assert seen > 0


# TC-P3 B 路自算缺口
def test_tc_p3_b_path_self_compute(db):
    cfg, user = db
    plan = _generate(cfg, user, req_overrides={"gap_report": None, "target_roles": ["RC002"], "target_skills": []})
    assert plan.phases
    assert plan.source_role == "RC002"


# TC-P4 持久化恢复
def test_tc_p4_persist_recover(db):
    cfg, user = db
    plan = _generate(cfg, user)
    from app.todo import todo_store

    loaded = todo_store.load_plan(cfg, plan.plan_id)
    assert loaded is not None
    assert loaded.phases and len(loaded.phases) == len(plan.phases)
    assert loaded.metrics.total_tasks == plan.metrics.total_tasks
    # 步骤明细应能随任务一并持久化并恢复
    loaded_steps = {t.skill_id: t.steps for ph in loaded.phases for t in ph.tasks}
    assert any(loaded_steps.values()), "持久化后步骤明细丢失"


# TC-P5 状态流转
def test_tc_p5_state_transition(db):
    cfg, user = db
    plan = _generate(cfg, user)
    task_id = plan.phases[0].tasks[0].task_id
    from app.todo import todo_store

    t1 = todo_store.transition_task(cfg, plan.plan_id, task_id, "start")
    assert t1.status == "doing"
    t2 = todo_store.transition_task(cfg, plan.plan_id, task_id, "complete")
    assert t2.status == "done"
    # 幂等
    t3 = todo_store.transition_task(cfg, plan.plan_id, task_id, "complete")
    assert t3.status == "done"


# TC-P6 非法流转
def test_tc_p6_illegal_transition(db):
    cfg, user = db
    plan = _generate(cfg, user)
    task_id = plan.phases[0].tasks[0].task_id
    from app.todo import todo_store

    with pytest.raises(ValueError):
        todo_store.transition_task(cfg, plan.plan_id, task_id, "complete")  # pending→done 非法


# TC-P7 可重复
def test_tc_p7_repeatable(db):
    cfg, user = db
    a = _generate(cfg, user, offline=True)
    b = _generate(cfg, user, offline=True)
    skill_groups_a = [[t.skill_id for t in ph.tasks] for ph in a.phases]
    skill_groups_b = [[t.skill_id for t in ph.tasks] for ph in b.phases]
    assert skill_groups_a == skill_groups_b


# TC-P8 重规划保留 done
def test_tc_p8_replan_keeps_done(db):
    cfg, user = db
    plan = _generate(cfg, user, req_overrides={"available_hours_per_week": 8})
    first_task = plan.phases[0].tasks[0]
    from app.todo import planner, todo_store
    from app.todo.schemas import ReplanRequest

    todo_store.transition_task(cfg, plan.plan_id, first_task.task_id, "start")
    todo_store.transition_task(cfg, plan.plan_id, first_task.task_id, "complete")
    new_plan = planner.replan(cfg, plan.plan_id, ReplanRequest(weekly_hours=40))
    done_skills = {t.skill_id for ph in new_plan.phases for t in ph.tasks if t.status == "done"}
    assert first_task.skill_id in done_skills


# TC-P9 LLM 兜底
def test_tc_p9_llm_fallback(db):
    cfg, user = db
    cfg.plan_llm_enabled = False
    plan = _generate(cfg, user, offline=True)
    assert plan.is_llm_enhanced is False
    assert plan.phases
    assert plan.goal.strip()


# TC-P10 非法入参 & 不存在（HTTP，无需 DB 部分走 client）
def test_tc_p10_invalid_input(client):
    resp = client.post(
        "/api/v1/plan/generate",
        json={"user_id": "U10001", "target_roles": [], "target_skills": [], "gap_report": None},
    )
    assert resp.status_code == 422
    body = resp.get_json()
    assert body["code"] == 42200
    assert "trace_id" in body
    # 坏 JSON → 400
    resp2 = client.post("/api/v1/plan/generate", data="not json", content_type="application/json")
    assert resp2.status_code == 400


# 计划不存在 → 404（需 DB）
def test_plan_not_found_404(db_client):
    resp = db_client.get("/api/v1/plan/PLAN_DOES_EXIST")
    assert resp.status_code == 404
    assert resp.get_json()["code"] == 40410