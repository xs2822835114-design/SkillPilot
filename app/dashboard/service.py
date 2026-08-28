"""Dashboard 聚合服务（阶段 8，只读）：画像 + 最新计划 + 最新评估 + 成长/事实。

聚合来自阶段 3~7 的存储层，无任何写操作、无业务规则新增；某部分不可用返回空值而非报错。
"""
from __future__ import annotations

import logging

from app.config import Config
from app.dashboard.schemas import (
    DashboardDTO,
    EvalSummary,
    GrowthEvent,
    MemoryFact,
    PlanSummary,
    ProfileSummary,
    SkillSummary,
)
from app.persistence import db as pgdb

logger = logging.getLogger(__name__)


def build(config: Config, user_id: str) -> DashboardDTO:
    dto = DashboardDTO(user_id=user_id)
    dto.profile = _profile(config, user_id)
    dto.latest_plan = _latest_plan(config, user_id)
    dto.latest_evaluation = _latest_evaluation(config, user_id)
    dto.growth = _growth(config, user_id)
    dto.facts = _facts(config, user_id)
    return dto


def _profile(config: Config, user_id: str) -> ProfileSummary:
    try:
        from app.profile import store as profile_store

        profile = profile_store.load_profile(config, user_id)
        return ProfileSummary(
            skill_count=len(profile.skills),
            skills=[
                SkillSummary(
                    skill_id=s.skill_id,
                    name=s.name or s.skill_id,
                    theory_score=int(s.theory_score or 0),
                    practice_score=int(s.practice_score or 0),
                    level=int(s.level or 0),
                )
                for s in profile.skills
            ],
        )
    except Exception:  # noqa: BLE001 - 某部分失败给空值，不阻断整体
        logger.warning("dashboard.profile 读取失败 user=%s", user_id, exc_info=True)
        return ProfileSummary()


def _latest_plan(config: Config, user_id: str) -> PlanSummary | None:
    from app.todo import todo_store

    plans = todo_store.list_plans(config, user_id, limit=1)
    if not plans:
        return None
    p = plans[0]
    return PlanSummary(
        plan_id=p["plan_id"],
        goal=p["goal"],
        status=p["status"],
        total_tasks=p["total_tasks"],
        done_tasks=p["done_tasks"],
        progress=p["progress"],
    )


def _latest_evaluation(config: Config, user_id: str) -> EvalSummary | None:
    with pgdb.connect(config) as conn:
        row = conn.execute(
            """
            SELECT id, skill_id, overall_score, replanned, created_at
            FROM evaluations
            WHERE user_id = %s
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (user_id,),
        ).fetchone()
    if not row:
        return None
    return EvalSummary(
        evaluation_id=row[0],
        skill_id=row[1] or "",
        overall_score=int(row[2] or 0),
        replanned=bool(row[3]),
        created_at=row[4],
    )


def _growth(config: Config, user_id: str) -> list[GrowthEvent]:
    try:
        from app.memory.service import query_events

        events = query_events(config, user_id, limit=10)
        return [
            GrowthEvent(
                id=e.get("id", ""),
                event_type=e.get("event_type", ""),
                summary=e.get("summary", "") or "",
                created_at=e.get("created_at"),
            )
            for e in events
        ]
    except Exception:  # noqa: BLE001
        logger.warning("dashboard.growth 读取失败 user=%s", user_id, exc_info=True)
        return []


def _facts(config: Config, user_id: str) -> list[MemoryFact]:
    try:
        items = _list_memories(config, user_id)
        return [MemoryFact(key=it["key"], text=it["text"], namespace=it["namespace"]) for it in items]
    except Exception:  # noqa: BLE001
        logger.warning("dashboard.facts 读取失败 user=%s", user_id, exc_info=True)
        return []


def _list_memories(config: Config, user_id: str) -> list[dict]:
    from app.memory import service as memory_service

    return [
        {"key": it.key, "text": it.text, "namespace": it.namespace}
        for it in memory_service.list_memories(config, user_id, None, limit=20)
    ]