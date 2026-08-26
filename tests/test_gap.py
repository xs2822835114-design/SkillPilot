"""阶段 4 Skill Graph / Gap 测试：TC-G1~G10。

规则类用例（gap_score/priority/closure/topo）为纯单元测试，始终运行；
集成用例依赖种子数据（skill_nodes/skill_edges/role_skills），未配置 DATABASE_URL 则跳过，
并在空库时自动执行 seed_skill_graph / seed_skills。
"""
from __future__ import annotations

import os
import uuid

import pytest

from app.gap import closure, gap_agent, gap_score
from app.gap.schemas import GapAnalysisRequest

U = lambda: "tu_g_" + uuid.uuid4().hex[:10]  # noqa: E731


# ---------------- 纯规则用例（不依赖 DB） ----------------


def test_gap_rules_score():
    assert gap_score.gap_score(4, 0, 1.0) == 0.8
    assert gap_score.gap_score(4, 2, 1.0) == 0.4      # delta=2
    assert gap_score.gap_score(4, 4, 1.0) == 0.0      # 已覆盖
    assert gap_score.gap_score(4, 0, 1.0, 0.5) == 0.4  # 前置衰减
    assert gap_score.gap_score(3, 0, 0.8) == pytest.approx(0.48)


def test_gap_rules_priority():
    assert gap_score.priority(0.95, 2) == "P1"
    assert gap_score.priority(0.9, 1) == "P2"   # w>=0.7 但 delta<2
    assert gap_score.priority(0.8, 2) == "P2"
    assert gap_score.priority(0.5, 2) == "P3"


def test_gap_rules_coverage_rate():
    assert gap_score.coverage_rate(3, 8) == pytest.approx(0.375)
    assert gap_score.coverage_rate(0, 0) == 0.0


def test_closure_transitive():
    # requires 边：source=前置, target=技能
    edges = [
        ("python", "llm_api"),
        ("llm_api", "langchain"),
        ("python", "langchain"),
        ("langchain", "langgraph"),
    ]
    assert closure.transitive_prereqs(edges, "langgraph") == {"python", "llm_api", "langchain"}
    assert closure.transitive_prereqs(edges, "python") == set()


def test_closure_topo_orders_prereqs_first():
    edges = [
        ("python", "llm_api"),
        ("llm_api", "langchain"),
        ("python", "langchain"),
        ("langchain", "langgraph"),
    ]
    seq = closure.topo_sort(["langgraph", "langchain", "python", "llm_api"], edges)
    pos = {s: i for i, s in enumerate(seq)}
    assert pos["python"] < pos["langchain"] < pos["langgraph"]
    assert pos["llm_api"] < pos["langchain"]


def test_closure_topo_cycle_fallback():
    edges = [("a", "b"), ("b", "a")]  # 环
    seq = closure.topo_sort(["a", "b", "c"], edges)
    assert len(seq) == 3 and set(seq) == {"a", "b", "c"}


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
    conn.execute("DELETE FROM user_skills WHERE user_id = %s", (user_id,))
    conn.execute("DELETE FROM user_preferences WHERE user_id = %s", (user_id,))


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


def _analyze(cfg, user, roles, offline=True):
    cfg.gap_llm_enabled = not offline
    return gap_agent.analyze(cfg, GapAnalysisRequest(user_id=user, target_roles=roles)).reports


# TC-G1 种子完备
def test_tc_g1_seed_complete(db):
    cfg, _ = db
    from app.persistence import db as pgdb

    with pgdb.connect(cfg) as c:
        nodes = c.execute("SELECT count(*) FROM skill_nodes").fetchone()[0]
        edges = c.execute("SELECT count(*) FROM skill_edges").fetchone()[0]
        rels = {r[0] for r in c.execute("SELECT DISTINCT rel FROM skill_edges").fetchall()}
        roles = c.execute("SELECT count(DISTINCT role_id) FROM role_skills").fetchone()[0]
    assert nodes > 0
    assert edges > 0
    assert rels >= {"requires", "composite_of", "related"}
    assert roles == 30


# TC-G2 岗位差异
def test_tc_g2_role_difference(db):
    cfg, user = db
    r2 = _analyze(cfg, user, ["RC002"])[0]
    r10 = _analyze(cfg, user, ["RC010"])[0]
    g2 = {g.skill_id for g in r2.gaps}
    g10 = {g.skill_id for g in r10.gaps}
    assert g2 != g10
    assert g2 != set()
    assert g10 != set()


# TC-G3 覆盖不入缺
def test_tc_g3_covered_excluded(db):
    cfg, user = db
    from app.profile.schemas import PatchSkill, SkillProfilePatch
    from app.profile import skill_service

    skill_service.apply_patch(
        cfg,
        SkillProfilePatch(
            user_id=user,
            skills=[PatchSkill(skill_id="java", theory_score=90, practice_score=95, confidence=1.0)],
        ),
    )
    rep = _analyze(cfg, user, ["RC010"])[0]
    assert "java" not in {g.skill_id for g in rep.gaps}
    assert "java" in rep.coverage.covered_skills
    assert rep.coverage.gap_total < rep.coverage.required_total


# TC-G4 字段齐全
def test_tc_g4_fields_complete(db):
    cfg, user = db
    rep = _analyze(cfg, user, ["RC002"])[0]
    assert rep.gaps
    for g in rep.gaps:
        assert g.priority in {"P1", "P2", "P3"}
        assert 0.0 <= g.score <= 1.0
        assert g.reason.strip()


# TC-G5 前置闭包
def test_tc_g5_prereq_closure(db):
    cfg, user = db
    rep = _analyze(cfg, user, ["RC002"])[0]
    lg = next((g for g in rep.gaps if g.skill_id == "langgraph"), None)
    assert lg is not None
    pre_names = {p.skill_id for p in lg.prerequisites}
    assert {"python", "langchain", "llm_api"} <= pre_names
    # recommended_sequence 拓扑有序：前置先于依赖
    seq = rep.recommended_sequence
    pos = {s: i for i, s in enumerate(seq)}
    for p in lg.prerequisites:
        if p.skill_id in pos and lg.skill_id in pos:
            assert pos[p.skill_id] < pos[lg.skill_id]


# TC-G6 评分可重复
def test_tc_g6_repeatable(db):
    cfg, user = db
    a = _analyze(cfg, user, ["RC002"])[0]
    b = _analyze(cfg, user, ["RC002"])[0]
    ma = {g.skill_id: (g.score, g.priority) for g in a.gaps}
    mb = {g.skill_id: (g.score, g.priority) for g in b.gaps}
    assert set(ma) == set(mb)
    for sid, (score, pri) in ma.items():
        assert mb[sid] == (score, pri)


# TC-G7 版本字段
def test_tc_g7_version(db):
    cfg, user = db
    rep = gap_agent.analyze(
        cfg, GapAnalysisRequest(user_id=user, target_roles=["RC002"], profile_version=12)
    ).reports[0]
    assert rep.profile_version_used == 12
    # 未传版本时取用户实际版本（默认 0）
    rep2 = _analyze(cfg, user, ["RC002"])[0]
    assert isinstance(rep2.profile_version_used, int)


# TC-G9 LLM 兜底
def test_tc_g9_llm_fallback(db):
    cfg, user = db
    cfg.gap_llm_enabled = False
    rep = gap_agent.analyze(
        cfg, GapAnalysisRequest(user_id=user, target_roles=["RC002"])
    ).reports[0]
    assert rep.is_llm_enhanced is False
    assert len(rep.gaps) > 0
    assert rep.suggestions.strip()  # 模板兜底仍给建议


# TC-G10 5 岗位测试集
def test_tc_g10_five_roles(db):
    cfg, user = db
    reports = _analyze(cfg, user, ["RC001", "RC002", "RC010", "RC025", "RC008"])
    assert len(reports) == 5
    for rep in reports:
        assert rep.coverage.gap_total > 0
        assert rep.gaps
        for g in rep.gaps:
            assert g.reason.strip()


# TC-G8 非法入参（422 + code 42200 + trace_id，无需 DB）
def test_tc_g8_invalid_input(client):
    # 无 target_roles 也无 target_skills → 422
    resp = client.post("/api/v1/gap/request", json={"user_id": "U10001", "target_roles": []})
    assert resp.status_code == 422
    body = resp.get_json()
    assert body["code"] == 42200
    assert "trace_id" in body
    # 坏 JSON → 400
    resp2 = client.post("/api/v1/gap/request", data="not json", content_type="application/json")
    assert resp2.status_code == 400


# 目标岗位不存在 → 422（需 DB）
def test_gap_unknown_role_422(db):
    cfg, user = db
    with pytest.raises(ValueError):
        gap_agent.analyze(cfg, GapAnalysisRequest(user_id=user, target_roles=["NOPE"]))