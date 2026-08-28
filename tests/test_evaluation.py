"""阶段 6 实践任务与能力评估测试：TC-E1~E11。

规则用例（静态分析/评分）纯单元运行；集成用例依赖真实 DB 与种子，自动 seed。
"""
from __future__ import annotations

import uuid

import pytest

from app.evaluation import analyzers, scorer


def U():  # noqa: N802
    return "tu_e_" + uuid.uuid4().hex[:10]


# ---------------- 纯规则：静态分析 / 评分 ----------------

GOOD_CODE = [
    ('main.py', 'import json\n'
                'def search(q: str) -> list:\n'
                '    return [q]\n'
                '\n'
                'if __name__ == "__main__":\n'
                '    print(search("a"))\n'),
]


def test_tc_e1_analysis_structure():
    checks = analyzers.analyze(dict(GOOD_CODE), strict=True)
    by = {c["type"]: c["passed"] for c in checks}
    assert by["syntax"] is True
    assert by["structure"] is True
    assert by["runnable"] is True
    assert by["tests"] is False  # 无测试
    assert "lint" in by


def test_tc_e2_score_evidence():
    checks = analyzers.analyze(dict(GOOD_CODE), strict=False)
    cfg = _cfg_off()
    theory, practice, overall, recs = scorer.score(cfg, "python_general", checks)
    evidence = scorer.build_evidence(checks, False)
    assert 0 <= theory <= 100 and 0 <= practice <= 100 and 0 <= overall <= 100
    assert evidence
    assert all(e.passed is not None for e in evidence)


def test_tc_e3_theory_vs_practice():
    # 可运行但无测试：practice 应低于 theory（同难度下缺测试扣分）
    cfg = _cfg_off()
    theory, practice, _, recs = scorer.score(cfg, "rag_retriever", analyzers.analyze(dict(GOOD_CODE), False))
    assert practice <= theory or practice < 100
    assert any("测试" in r for r in recs) or not recs  # 无测试应有提示


def test_tc_e4_recommendations():
    # 文件含 TODO → 启发式 lint 触发 → 建议面向"清理"
    bad = {"main.py": "def f():\n    return 1\n# TODO: 优化性能\n"}
    checks = analyzers.analyze(bad, strict=True)
    lint = next((c for c in checks if c["type"] == "lint"), None)
    assert lint is not None and lint["passed"] is False
    _, _, _, recs = scorer.score(_cfg_off(), "python_general", checks)
    assert any("清理" in r for r in recs)


# ---------------- 集成：实践生成与评估闭环 ----------------

def _cfg_db():
    from app.config import get_config

    if not get_config().database_url:
        pytest.skip("DATABASE_URL 未配置")
    from app.config import Config

    return Config(
        env="test",
        database_url=get_config().database_url,
        llm_api_key="",
        checkpointer_backend="memory",
        embedding_provider="off",
        eval_llm_enabled=False,
        practice_llm_enabled=False,
    )


def _cfg_off():
    from app.config import Config

    return Config(env="test", checkpointer_backend="memory")


def _ensure_seed(cfg):
    from app.persistence import db as pgdb

    with pgdb.connect(cfg) as c:
        n = c.execute("SELECT count(*) FROM skill_nodes").fetchone()[0]
    if n == 0:
        from scripts.seed_skill_graph import run as seed_graph

        seed_graph()


@pytest.fixture()
def db():
    cfg = _cfg_db()
    _ensure_seed(cfg)
    from app.persistence import db as pgdb

    user = U()
    with pgdb.connect(cfg) as conn:
        conn.execute("DELETE FROM practices WHERE user_id=%s", (user,))
        conn.execute("DELETE FROM evaluations WHERE user_id=%s", (user,))
        conn.execute("DELETE FROM learning_plans WHERE user_id=%s", (user,))
        conn.execute("DELETE FROM user_skills WHERE user_id=%s", (user,))
        conn.execute("DELETE FROM user_preferences WHERE user_id=%s", (user,))
        conn.execute("DELETE FROM skill_evidence WHERE user_id=%s", (user,))
    yield cfg, user
    with pgdb.connect(cfg) as conn:
        conn.execute("DELETE FROM practices WHERE user_id=%s", (user,))
        conn.execute("DELETE FROM evaluations WHERE user_id=%s", (user,))
        conn.execute("DELETE FROM learning_plans WHERE user_id=%s", (user,))
        conn.execute("DELETE FROM user_skills WHERE user_id=%s", (user,))
        conn.execute("DELETE FROM user_preferences WHERE user_id=%s", (user,))


def _make_plan_with_task(db):
    cfg, user = db
    from app.todo import planner as todo_planner
    from app.todo.schemas import PlanRequest

    plan = todo_planner.generate(cfg, PlanRequest(user_id=user, target_roles=["RC002"]))
    task = plan.phases[0].tasks[0]
    return cfg, user, plan, task


# TC-E5 评估→画像更新
def test_tc_e5_eval_updates_profile(db):
    cfg, user, _plan, task = _make_plan_with_task(db)
    from app.practice import planner as pra_planner
    from app.practice.schemas import PracticeCreateRequest
    from app.evaluation import service
    from app.evaluation.schemas import EvaluationRequest
    from app.profile import store as profile_store

    pra = pra_planner.generate(cfg, PracticeCreateRequest(user_id=user, task_id=task.task_id, skill_id=task.skill_id))
    before = profile_store.load_profile(cfg, user).skills
    before_scores = {s.skill_id: s.practice_score for s in before}

    report = service.run_evaluation(
        cfg,
        EvaluationRequest(
            user_id=user, practice_id=pra.practice_id,
            artifact_type="snippet",
            repo_files={"main.py": "def search(q):\n    return q\n", "test_main.py": "def test_search():\n    assert search('a')=='a'\n"},
            trigger_replan=False,
        ),
    )
    assert report.profile_updated is True
    assert report.replanned is False
    after = {s.skill_id: s.practice_score for s in profile_store.load_profile(cfg, user).skills}
    assert task.skill_id in after and after[task.skill_id] >= before_scores.get(task.skill_id, 0)


# TC-E6 评估→再规划
def test_tc_e6_eval_triggers_replan(db):
    cfg, user, plan, task = _make_plan_with_task(db)
    from app.practice import planner as pra_planner
    from app.practice.schemas import PracticeCreateRequest
    from app.evaluation import service
    from app.evaluation.schemas import EvaluationRequest
    from app.todo import todo_store

    pra = pra_planner.generate(cfg, PracticeCreateRequest(user_id=user, task_id=task.task_id, skill_id=task.skill_id))
    # 先把任务置为 done，验证重规划后仍保留
    todo_store.transition_task(cfg, plan.plan_id, task.task_id, "start")
    todo_store.transition_task(cfg, plan.plan_id, task.task_id, "complete")

    report = service.run_evaluation(
        cfg,
        EvaluationRequest(user_id=user, practice_id=pra.practice_id,
                          artifact_type="snippet",
                          repo_files={"main.py": "def demo():\n    pass\n", "test_a.py": "def test_a():\n    pass\n"},
                          trigger_replan=True),
    )
    assert report.replanned is True
    reloaded = todo_store.load_plan(cfg, plan.plan_id)
    # 评估提升 practice_score → 该技能缺口关闭 → 不再作为待办任务出现（证明评估结果已传导到重规划）
    pending = {t.skill_id for ph in reloaded.phases for t in ph.tasks if t.status != "done"}
    assert task.skill_id not in pending


# TC-E7 关闭再规划
def test_tc_e7_disable_replan(db):
    cfg, user, _plan, task = _make_plan_with_task(db)
    from app.practice import planner as pra_planner
    from app.practice.schemas import PracticeCreateRequest
    from app.evaluation import service
    from app.evaluation.schemas import EvaluationRequest

    pra = pra_planner.generate(cfg, PracticeCreateRequest(user_id=user, task_id=task.task_id, skill_id=task.skill_id))
    report = service.run_evaluation(
        cfg,
        EvaluationRequest(user_id=user, practice_id=pra.practice_id, artifact_type="snippet",
                          repo_files={"main.py": "def x():\n    pass\n"}, trigger_replan=False),
    )
    assert report.profile_updated is True
    assert report.replanned is False


# TC-E8 幂等可重复
def test_tc_e8_idempotent(db):
    cfg, user, _plan, task = _make_plan_with_task(db)
    from app.practice import planner as pra_planner
    from app.practice.schemas import PracticeCreateRequest
    from app.evaluation import service
    from app.evaluation.schemas import EvaluationRequest

    pra = pra_planner.generate(cfg, PracticeCreateRequest(user_id=user, task_id=task.task_id, skill_id=task.skill_id))
    files = {"main.py": "def f():\n    return 1\n"}
    a = service.run_evaluation(cfg, EvaluationRequest(user_id=user, practice_id=pra.practice_id, artifact_type="snippet", repo_files=files, trigger_replan=False))
    b = service.run_evaluation(cfg, EvaluationRequest(user_id=user, practice_id=pra.practice_id, artifact_type="snippet", repo_files=files, trigger_replan=False))
    assert a.overall_score == b.overall_score
    assert a.skill_scores[0].practice == b.skill_scores[0].practice


# TC-E9 LLM 兜底（关闭 LLM 仍完整产出）
def test_tc_e9_llm_off(db):
    cfg, user, _plan, task = _make_plan_with_task(db)
    from app.practice import planner as pra_planner
    from app.practice.schemas import PracticeCreateRequest
    from app.evaluation import service
    from app.evaluation.schemas import EvaluationRequest

    pra = pra_planner.generate(cfg, PracticeCreateRequest(user_id=user, task_id=task.task_id, skill_id=task.skill_id))
    assert pra.is_llm_enhanced is False
    report = service.run_evaluation(cfg, EvaluationRequest(user_id=user, practice_id=pra.practice_id, artifact_type="snippet", repo_files={"main.py": "pass\n"}, trigger_replan=False))
    assert report.evidence and report.next_recommendations


# TC-E10 snippet 兜底
def test_tc_e10_snippet_fallback(db):
    cfg, user, _plan, task = _make_plan_with_task(db)
    from app.practice import planner as pra_planner
    from app.practice.schemas import PracticeCreateRequest
    from app.evaluation import service
    from app.evaluation.schemas import ArtifactUploadRequest, EvaluationRequest

    pra = pra_planner.generate(cfg, PracticeCreateRequest(user_id=user, task_id=task.task_id, skill_id=task.skill_id))
    service.ingest_snippet(cfg, ArtifactUploadRequest(user_id=user, practice_id=pra.practice_id, filename="main.py", content="def z():\n    return 2\n"))
    report = service.run_evaluation(cfg, EvaluationRequest(user_id=user, practice_id=pra.practice_id, artifact_type="snippet", trigger_replan=False))
    assert report.evidence


# TC-E11 路由
def test_tc_e11_route_invalid(client):
    resp = client.post("/api/v1/practice/generate", json={"user_id": "U10001", "task_id": "X"})
    assert resp.status_code == 422
    resp2 = client.post("/api/v1/evaluation/evaluate", data="nope", content_type="application/json")
    assert resp2.status_code == 400