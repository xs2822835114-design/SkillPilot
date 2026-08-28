"""评估存储（阶段 6，evaluation/store）：evaluations / code_snippets 持久化（psycopg 直连）。"""
from __future__ import annotations

import logging

from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from app.config import Config
from app.evaluation.schemas import ArtifactUploadRequest, EvaluationReport
from app.persistence import db as pgdb

logger = logging.getLogger(__name__)


def create_snippet(config: Config, req: ArtifactUploadRequest, snippet_id: str) -> None:
    with pgdb.connect(config) as conn:
        conn.execute(
            """
            INSERT INTO code_snippets (id, user_id, practice_id, language, filename, content, created_at)
            VALUES (%s, %s, %s, %s, %s, %s, now())
            ON CONFLICT (id) DO NOTHING
            """,
            (snippet_id, req.user_id, req.practice_id, req.language, req.filename, req.content),
        )


def save_evaluation(
    config: Config,
    report: EvaluationReport,
    user_id: str,
    artifact_type: str,
    artifact_ref: str | None,
) -> None:
    with pgdb.connect(config) as conn:
        conn.execute(
            """
            INSERT INTO evaluations
              (id, practice_id, user_id, artifact_type, artifact_ref, skill_id,
               overall_score, report_json, profile_updated, replanned, created_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, now())
            ON CONFLICT (id) DO UPDATE SET
              overall_score=EXCLUDED.overall_score, report_json=EXCLUDED.report_json,
              profile_updated=EXCLUDED.profile_updated, replanned=EXCLUDED.replanned
            """,
            (
                report.evaluation_id,
                report.practice_id,
                user_id,
                artifact_type,
                artifact_ref,
                report.skill_id,
                report.overall_score,
                Jsonb(report.model_dump(mode="json")),
                report.profile_updated,
                report.replanned,
            ),
        )


def load_evaluation(config: Config, evaluation_id: str) -> EvaluationReport | None:
    with pgdb.connect(config) as conn:
        conn.row_factory = dict_row
        row = conn.execute(
            "SELECT report_json FROM evaluations WHERE id = %s", (evaluation_id,)
        ).fetchone()
        if not row or not row["report_json"]:
            return None
    return EvaluationReport(**row["report_json"])


def load_snippets_for_practice(config: Config, practice_id: str) -> dict[str, str]:
    """将该实践已上传的代码片段组装为 {filename: content} 字典。"""
    with pgdb.connect(config) as conn:
        conn.row_factory = dict_row
        rows = conn.execute(
            "SELECT filename, content FROM code_snippets "
            "WHERE practice_id = %s ORDER BY created_at ASC",
            (practice_id,),
        ).fetchall()
    out: dict[str, str] = {}
    for r in rows:
        key = r["filename"] or f"file_{len(out)}.py"
        out[key] = r["content"] or ""
    return out