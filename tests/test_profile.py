"""阶段 3 画像测试：TC-P1~P10。

规则类用例（等级换算/置信度合并）为纯单元测试，始终运行；
其余用例如未配置 DATABASE_URL 则跳过（依赖真实 PostgreSQL）。
"""
from __future__ import annotations

import os
import uuid

import pytest

from app.config import get_config
from app.profile import rule_engine, skill_service

U = lambda: "tu_" + uuid.uuid4().hex[:10]  # noqa: E731


# ---- 纯规则用例（不依赖 DB） ----

def test_tc_p2_level_conversion():
    # theory=80, practice=85, w=0.6 → raw=0.4*80+0.6*85=83 → level=4
    assert rule_engine.level_from_scores(80, 85) == 4
    assert rule_engine.level_from_scores(100, 100) == 5
    assert rule_engine.level_from_scores(0, 0) == 0
    # theory=95, practice=10, w=0.6 → 0.4*95+0.6*10=44 → level=2
    assert rule_engine.level_from_scores(95, 10, 0.6) == 2


def test_tc_p6_confidence_merge():
    assert rule_engine.merge_confidence(0.9, 0.5) == pytest.approx(0.66)
    assert rule_engine.merge_confidence(None, 0.5) == pytest.approx(0.3)  # 0.4*0+0.6*0.5
    assert rule_engine.merge_confidence(0.5, None) == pytest.approx(0.2)


def test_tc_p11_normalize_slug():
    assert skill_service.normalize_skill_id("Spring Boot") == "spring_boot"
    assert skill_service.normalize_skill_id("Vector DB") == "vector_db"
    assert skill_service.normalize_skill_id(" RAG ") == "rag"


# ---- 集成用例（依赖真实 DB，未配置则跳过） ----

def _cfg_db():
    db = get_config().database_url
    if not db:
        pytest.skip("DATABASE_URL 未配置，跳过 DB 集成用例")
    return get_config()


def _clean(conn, user_id):
    for sql in (
        "DELETE FROM user_skills WHERE user_id = %s",
        "DELETE FROM projects WHERE user_id = %s",
        "DELETE FROM user_preferences WHERE user_id = %s",
        "DELETE FROM skill_evidence WHERE user_id = %s",
    ):
        conn.execute(sql, (user_id,))


@pytest.fixture()
def db():
    cfg = _cfg_db()
    from app.persistence import db as pgdb

    user = U()
    with pgdb.connect(cfg) as conn:
        _clean(conn, user)
    yield cfg, user
    with pgdb.connect(cfg) as conn:
        _clean(conn, user)


def test_tc_p1_empty_profile(db):
    cfg, user = db
    from app.profile.store import load_profile

    p = load_profile(cfg, user)
    assert p.skills == [] and p.version == 0


def test_tc_p3_basic_upsert(db):
    cfg, user = db
    from app.profile.schemas import PatchSkill, SkillProfilePatch

    patch = SkillProfilePatch(
        user_id=user,
        skills=[PatchSkill(skill_id="spring_boot", theory_score=80, practice_score=85, confidence=0.9)],
    )
    p = skill_service.apply_patch(cfg, patch)
    assert p.version == 1
    assert len(p.skills) == 1
    assert p.skills[0].skill_id == "spring_boot"
    assert p.skills[0].level == 4


def test_tc_p4_incremental_no_overwrite(db):
    cfg, user = db
    from app.profile.schemas import PatchSkill, SkillProfilePatch

    base = SkillProfilePatch(
        user_id=user,
        skills=[
            PatchSkill(skill_id="spring_boot", theory_score=80, practice_score=85, confidence=0.9),
            PatchSkill(skill_id="mysql", theory_score=70, practice_score=75, confidence=0.8),
        ],
    )
    skill_service.apply_patch(cfg, base)

    # 第二次只改 spring_boot，mysql 应保持不变
    patch2 = SkillProfilePatch(
        user_id=user, skills=[PatchSkill(skill_id="spring_boot", theory_score=90, confidence=1.0)]
    )
    p2 = skill_service.apply_patch(cfg, patch2)
    skills = {s.skill_id: s for s in p2.skills}
    assert skills["spring_boot"].theory_score == 90
    assert skills["mysql"].practice_score == 75  # 未被改动
    assert p2.version == 2


def test_tc_p5_null_field_keeps_old(db):
    cfg, user = db
    from app.profile.schemas import PatchSkill, SkillProfilePatch

    base = SkillProfilePatch(
        user_id=user, skills=[PatchSkill(skill_id="mysql", theory_score=70, practice_score=75, confidence=0.8)]
    )
    skill_service.apply_patch(cfg, base)

    p2 = skill_service.apply_patch(
        cfg, SkillProfilePatch(user_id=user, skills=[PatchSkill(skill_id="mysql", theory_score=90)])
    )
    s = next(x for x in p2.skills if x.skill_id == "mysql")
    assert s.practice_score == 75  # 未提供 → 保持旧值


def test_tc_p8_project_bind(db):
    cfg, user = db
    p = skill_service.register_project(
        cfg, user, "PROJ_T", "订单系统", "基于 Spring Boot 与 MySQL 与 Redis 的订单系统", []
    )
    proj = next(x for x in p.projects if x.project_id == "PROJ_T")
    assert "spring_boot" in proj.skills
    assert "mysql" in proj.skills
    assert any(s.skill_id == "spring_boot" for s in p.skills)


def test_tc_p9_llm_off_fallback(db):
    cfg, user = db
    from app.profile import extractor
    from app.profile.schemas import ProfileExtractionRequest
    from app.profile.store import load_skill_names

    cfg.profile_llm_enabled = False
    names = [r["name"] for r in load_skill_names(cfg)]
    req = ProfileExtractionRequest(user_id=user, content="我会 Java 和 Spring Boot，做过订单系统")
    res = extractor.extract(cfg, req, names)
    assert res.status == "extracted"
    assert isinstance(res.patch.skills, list)
    assert any("java" in s.skill_id.lower() for s in res.patch.skills)


def test_tc_p10_validation(client, app):
    # 非法 user_id → 422 + code 42200
    resp = client.post(
        "/api/v1/profile/upsert", json={"user_id": "###", "skills": []}
    )
    assert resp.status_code == 422
    body = resp.get_json()
    assert body["code"] == 42200
    assert "trace_id" in body