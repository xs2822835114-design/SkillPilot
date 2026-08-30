"""教学会话存储：优先 PostgreSQL 持久化，未配置 DATABASE_URL 时回退内存（测试/Demo）。

关键设计（对齐「新任务重置，同任务恢复」）：
- 稳定身份：user_id + task_id 唯一确定一个学习会话。用户反复点击同一任务的
  「开始学习」都会命中同一个 session（load_by_task），不会新建空会话；关闭窗口、
  刷新页面、进程重启后，再次进入同一任务都能恢复 opening / content / turns / status。
- 新任务（task_id 不同）自然查到不同记录，天然隔离，不会串状态。
- 记录教学回合（teaching_turns），供多轮互动与历史消息恢复。
"""
from __future__ import annotations

import logging
import threading

from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from app.config import Config
from app.persistence import db as pgdb
from app.teaching.schemas import (
    ROLE_AI,
    ROLE_USER,
    TeachingContent,
    TeachingSession,
    TeachingTurn,
)

logger = logging.getLogger(__name__)

# 无 DB 时的进程内兜底（保持现有测试与单进程 Demo 形态）
_mem_lock = threading.Lock()
_mem: dict[str, TeachingSession] = {}


# ---------------- 写入 ----------------

def _ensure_columns(conn) -> None:
    """幂等补齐历史库可能缺少的列（新库由 init_db 建表时已含）。"""
    conn.execute("ALTER TABLE teaching_sessions ADD COLUMN IF NOT EXISTS status VARCHAR(24) DEFAULT 'active'")
    conn.execute("ALTER TABLE teaching_sessions ADD COLUMN IF NOT EXISTS current_step INT DEFAULT 0")


def _db_save(config: Config, session: TeachingSession) -> None:
    with pgdb.connect(config) as conn:
        _ensure_columns(conn)
        conn.execute(
            """
            INSERT INTO teaching_sessions
              (session_id, user_id, plan_id, task_id, title, learning_objective,
               acceptance_criteria, opening, content_json, status, current_step,
               created_at, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, now(), now())
            ON CONFLICT (session_id) DO UPDATE SET
              title=EXCLUDED.title,
              learning_objective=EXCLUDED.learning_objective,
              acceptance_criteria=EXCLUDED.acceptance_criteria,
              opening=EXCLUDED.opening,
              content_json=EXCLUDED.content_json,
              status=EXCLUDED.status,
              current_step=EXCLUDED.current_step,
              updated_at=now()
            """,
            (
                session.session_id,
                session.user_id,
                session.plan_id,
                session.task_id,
                session.title,
                session.learning_objective,
                session.acceptance_criteria,
                session.opening,
                Jsonb(session.content.model_dump()),
                session.status,
                session.current_step,
            ),
        )
        conn.execute("DELETE FROM teaching_turns WHERE session_id = %s", (session.session_id,))
        for turn in session.turns:
            conn.execute(
                """
                INSERT INTO teaching_turns (session_id, role, message, mode, content_json)
                VALUES (%s, %s, %s, %s, %s)
                """,
                (
                    session.session_id,
                    turn.role,
                    turn.message,
                    turn.mode,
                    Jsonb(turn.content.model_dump()) if turn.content else None,
                ),
            )


def save(config: Config, session: TeachingSession) -> TeachingSession:
    """持久化整个会话（含回合）。无 DB 时落内存兜底。失败仅告警，不抛异常阻断教学。"""
    if config.database_url:
        try:
            _db_save(config, session)
            return session
        except Exception:  # noqa: BLE001 - 持久化失败不阻断本轮教学
            logger.warning("teaching session 落库失败 session=%s", session.session_id, exc_info=True)
    with _mem_lock:
        _mem[session.session_id] = session
    return session


# ---------------- 读取 ----------------

def _db_load(config: Config, session_id: str) -> TeachingSession | None:
    with pgdb.connect(config) as conn:
        _ensure_columns(conn)
        conn.row_factory = dict_row
        row = conn.execute(
            "SELECT * FROM teaching_sessions WHERE session_id = %s", (session_id,)
        ).fetchone()
        if not row:
            return None
        turns = conn.execute(
            "SELECT role, message, mode, content_json FROM teaching_turns "
            "WHERE session_id = %s ORDER BY id",
            (session_id,),
        ).fetchall()
    content = TeachingContent(**(row["content_json"] or {}))
    session = TeachingSession(
        session_id=row["session_id"],
        plan_id=row["plan_id"] or "",
        task_id=row["task_id"] or "",
        user_id=row["user_id"] or "",
        title=row["title"] or "",
        learning_objective=row["learning_objective"] or "",
        acceptance_criteria=row["acceptance_criteria"] or "",
        opening=row["opening"] or "",
        content=content,
        status=row["status"] or "active",
        current_step=int(row["current_step"] or 0),
        turns=[TeachingTurn(
            role=t["role"],
            message=t["message"] or "",
            mode=t["mode"] or "explain",
            content=TeachingContent(**(t["content_json"] or {})) if t["content_json"] else None,
        ) for t in turns],
    )
    return session


def load(config: Config, session_id: str) -> TeachingSession | None:
    if config.database_url:
        sess = _db_load(config, session_id)
        if sess is not None:
            return sess
        with _mem_lock:
            return _mem.get(session_id)
    with _mem_lock:
        return _mem.get(session_id)


def load_by_task(config: Config, user_id: str, task_id: str) -> TeachingSession | None:
    """稳定恢复：按 user_id + task_id 定位该学习任务的既有会话（含历史回合）。"""
    if not user_id or not task_id:
        return None
    if config.database_url:
        try:
            with pgdb.connect(config) as conn:
                _ensure_columns(conn)
                conn.row_factory = dict_row
                row = conn.execute(
                    "SELECT session_id FROM teaching_sessions "
                    "WHERE user_id = %s AND task_id = %s "
                    "ORDER BY updated_at DESC LIMIT 1",
                    (user_id, task_id),
                ).fetchone()
            if row:
                return _db_load(config, row["session_id"])
        except Exception:  # noqa: BLE001
            logger.warning("load_by_task 查询失败", exc_info=True)
            return None
    with _mem_lock:
        for s in _mem.values():
            if s.user_id == user_id and s.task_id == task_id:
                return s
    return None


# ---------------- 兼容别名（供历史调用/外部测试快速引用） ----------------

def put(config: Config, session: TeachingSession) -> TeachingSession:
    return save(config, session)


def get(config: Config, session_id: str) -> TeachingSession | None:
    return load(config, session_id)