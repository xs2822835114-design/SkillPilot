"""实践任务存储（阶段 6，practice/store）（psycopg 直连）。"""
from __future__ import annotations

import logging

from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from app.config import Config
from app.persistence import db as pgdb
from app.practice.schemas import PracticePlan

logger = logging.getLogger(__name__)


def create_practice(config: Config, plan: PracticePlan) -> PracticePlan:
    with pgdb.connect(config) as conn:
        conn.execute(
            """
            INSERT INTO practices
              (id, plan_id, task_id, user_id, skill_id, format, level_target,
               deliverables_json, rubric_json, status, is_llm_enhanced, created_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (id) DO UPDATE SET
              level_target=EXCLUDED.level_target, deliverables_json=EXCLUDED.deliverables_json,
              rubric_json=EXCLUDED.rubric_json, is_llm_enhanced=EXCLUDED.is_llm_enhanced
            """,
            (
                plan.practice_id,
                plan.plan_id,
                plan.task_id,
                plan.user_id,
                plan.skill_id,
                plan.format,
                plan.level_target,
                Jsonb([d.model_dump() for d in plan.deliverables]),
                Jsonb([r.model_dump() for r in plan.rubric]),
                "pending",
                plan.is_llm_enhanced,
                plan.created_at,
            ),
        )
    return plan


def load_practice(config: Config, practice_id: str) -> PracticePlan | None:
    with pgdb.connect(config) as conn:
        conn.row_factory = dict_row
        row = conn.execute(
            "SELECT * FROM practices WHERE id = %s", (practice_id,)
        ).fetchone()
        if not row:
            return None
    return PracticePlan(
        practice_id=row["id"],
        user_id=row["user_id"],
        plan_id=row["plan_id"] or "",
        task_id=row["task_id"] or "",
        skill_id=row["skill_id"] or "",
        level_target=int(row["level_target"] or 1),
        format=row["format"] or "project",
        created_at=row["created_at"],
        is_llm_enhanced=bool(row["is_llm_enhanced"]),
        deliverables=row["deliverables_json"] or [],
        rubric=row["rubric_json"] or [],
        guide="",
    )