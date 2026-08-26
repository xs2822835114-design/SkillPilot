"""阶段 7 经历记忆（memory/episodic）：阶段 3~6 关键动作沉淀为 Episode（append-only）。

record_event / query_events；event_type 受契约约束（EVENT_TYPES）。best-effort，不感知 HTTP。
"""
from __future__ import annotations

import logging
import uuid

from app.config import Config
from app.memory import store
from app.memory.schemas import EVENT_TYPES, Episode, EpisodeRequest

logger = logging.getLogger(__name__)


def _new_id() -> str:
    return f"EVT_{uuid.uuid4().hex[:12]}"


def record(config: Config, req: EpisodeRequest) -> str:
    """写入一条经历记忆；event_type 非法时抛 ValueError。"""
    if req.event_type not in EVENT_TYPES:
        raise ValueError(f"非法事件类型：{req.event_type}")
    ep = Episode(
        event_id=_new_id(),
        user_id=req.user_id,
        event_type=req.event_type,
        ref_ids=req.ref_ids,
        summary=req.summary,
        payload=req.payload,
    )
    return store.append_event(config, ep)


def query(
    config: Config, user_id: str, event_type: str | None = None, limit: int = 20
) -> list[dict]:
    """回查成长轨迹（默认倒序，最新优先）。"""
    return store.query_events(config, user_id, event_type, limit)