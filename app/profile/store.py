"""画像存储（阶段 3）：user_skills / projects / user_preferences 读写（psycopg 直连）。"""
from __future__ import annotations

import logging
from typing import Any

from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from app.config import Config
from app.persistence import db as pgdb
from app.profile.schemas import ProfileSkill, ProjectInfo, SkillProfile

logger = logging.getLogger(__name__)

# 画像版本号存于 user_preferences 的保留键（SkillProfile.version 需跨更新持久化）
VERSION_KEY = "__profile_version__"


# ---------------- 技能字典 ----------------

def load_skill_names(config: Config) -> list[dict]:
    with pgdb.connect(config) as conn:
        conn.row_factory = dict_row
        rows = conn.execute("SELECT id, name, category FROM skills").fetchall()
    return [dict(r) for r in rows]


def ensure_skill_in_dict(config: Config, skill_id: str) -> None:
    """确保 skill_id 存在于技能字典（user_skills 外键约束）；不存在则以 id 兜底插入。"""
    with pgdb.connect(config) as conn:
        conn.execute(
            """
            INSERT INTO skills (id, name, category, description)
            VALUES (%s, %s, 'evaluated', '由能力评估自动补录的学习技能节点')
            ON CONFLICT (id) DO NOTHING
            """,
            (skill_id, skill_id),
        )


# ---------------- 画像读写 ----------------

def load_profile(config: Config, user_id: str) -> SkillProfile:
    skills = _load_user_skills(config, user_id)
    projects = _load_projects(config, user_id)
    prefs = _load_preferences(config, user_id)
    version = int(prefs.pop(VERSION_KEY, 0) or 0)
    return SkillProfile(
        user_id=user_id,
        version=version,
        skills=skills,
        projects=projects,
        preferences=prefs,
    )


def save_patch(config: Config, user_id: str, profile: SkillProfile) -> None:
    asset_scores(profile)
    with pgdb.connect(config) as conn:
        for s in profile.skills:
            conn.execute(
                """
                INSERT INTO user_skills
                  (user_id, skill_id, theory_score, practice_score, confidence, last_proven_at)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (user_id, skill_id) DO UPDATE SET
                  theory_score   = EXCLUDED.theory_score,
                  practice_score = EXCLUDED.practice_score,
                  confidence     = EXCLUDED.confidence,
                  last_proven_at = COALESCE(EXCLUDED.last_proven_at, user_skills.last_proven_at),
                  updated_at     = now()
                """,
                (user_id, s.skill_id, s.theory_score, s.practice_score, s.confidence, s.last_proven_at),
            )
        _save_preferences(conn, user_id, profile.preferences)
        # 持久化画像版本
        conn.execute(
            """
            INSERT INTO user_preferences (user_id, key, value)
            VALUES (%s, %s, %s)
            ON CONFLICT (user_id, key) DO UPDATE SET value = EXCLUDED.value, updated_at = now()
            """,
            (user_id, VERSION_KEY, Jsonb(profile.version)),
        )


def _load_user_skills(config: Config, user_id: str) -> list[ProfileSkill]:
    with pgdb.connect(config) as conn:
        conn.row_factory = dict_row
        rows = conn.execute(
            """
            SELECT us.skill_id, s.name, us.theory_score, us.practice_score, us.confidence,
                   us.last_proven_at, us.updated_at
            FROM user_skills us
            JOIN skills s ON s.id = us.skill_id
            WHERE us.user_id = %s
            ORDER BY us.confidence DESC
            """,
            (user_id,),
        ).fetchall()
    result = []
    for r in rows:
        ev = _load_evidence(config, user_id, r["skill_id"])
        sk = ProfileSkill(
            skill_id=r["skill_id"],
            name=r["name"] or r["skill_id"],
            level=0,
            theory_score=r["theory_score"] or 0,
            practice_score=r["practice_score"] or 0,
            confidence=r["confidence"] or 0.0,
            last_proven_at=r["last_proven_at"],
            evidence=ev,
        )
        result.append(sk)
    asset_scores_skills(result)
    return result


def asset_scores_skills(skills: list[ProfileSkill]) -> None:
    from app.profile import rule_engine

    for s in skills:
        s.level = rule_engine.level_from_scores(s.theory_score, s.practice_score)


def asset_scores(profile: SkillProfile) -> None:
    from app.profile import rule_engine

    for s in profile.skills:
        s.level = rule_engine.level_from_scores(s.theory_score, s.practice_score)


def _load_evidence(config: Config, user_id: str, skill_id: str) -> list[str]:
    # 当前以"该用户所有证据"按最近取一部分（简单实现，完整记忆留阶段 7）
    rows = _load_all_evidence(config, user_id)
    return [r["id"] for r in rows]


def _load_all_evidence(config: Config, user_id: str) -> list[dict]:
    with pgdb.connect(config) as conn:
        conn.row_factory = dict_row
        rows = conn.execute(
            "SELECT id FROM skill_evidence WHERE user_id = %s ORDER BY extracted_at DESC LIMIT 20",
            (user_id,),
        ).fetchall()
    return [dict(r) for r in rows]


# ---------------- 偏好 ----------------

def _load_preferences(config: Config, user_id: str) -> dict[str, Any]:
    with pgdb.connect(config) as conn:
        conn.row_factory = dict_row
        rows = conn.execute(
            "SELECT key, value FROM user_preferences WHERE user_id = %s",
            (user_id,),
        ).fetchall()
    return {r["key"]: r["value"] for r in rows if r["value"] is not None}


def _save_preferences(conn, user_id: str, prefs: dict[str, Any]) -> None:
    for k, v in prefs.items():
        conn.execute(
            """
            INSERT INTO user_preferences (user_id, key, value, updated_at)
            VALUES (%s, %s, %s, now())
            ON CONFLICT (user_id, key) DO UPDATE SET value = EXCLUDED.value, updated_at = now()
            """,
            (user_id, k, Jsonb(v)),
        )


# ---------------- 项目 ----------------

def _load_projects(config: Config, user_id: str) -> list[ProjectInfo]:
    with pgdb.connect(config) as conn:
        conn.row_factory = dict_row
        rows = conn.execute(
            "SELECT id, name, skills FROM projects WHERE user_id = %s ORDER BY created_at DESC",
            (user_id,),
        ).fetchall()
    return [
        ProjectInfo(project_id=r["id"], name=r["name"] or "", skills=list(r["skills"] or []))
        for r in rows
    ]


def upsert_project(config: Config, user_id: str, project: ProjectInfo) -> None:
    with pgdb.connect(config) as conn:
        conn.execute(
            """
            INSERT INTO projects (id, user_id, name, skills)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (id) DO UPDATE SET
              name = EXCLUDED.name, skills = EXCLUDED.skills
            """,
            (project.project_id, user_id, project.name, list(project.skills)),
        )


def save_evidence(config: Config, evidence_id: str, user_id: str, source_ref: str, claim: str) -> None:
    with pgdb.connect(config) as conn:
        conn.execute(
            """
            INSERT INTO skill_evidence (id, user_id, source_type, source_ref, claim)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (id) DO NOTHING
            """,
            (evidence_id, user_id, "project", source_ref, claim),
        )