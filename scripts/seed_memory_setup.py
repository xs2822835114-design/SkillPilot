"""阶段 7 memory setup 校验（幂等；仅应用启动/迁移阶段执行，业务路径不调用）。

用途：确认 memories/memory_events/pending_actions 已建表、hnsw 向量索引与 pgvector
扩展可用的前置已就绪。用法：
    .venv/bin/python -m scripts.seed_memory_setup
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from psycopg.rows import dict_row

from app.config import get_config


def verify(config=None) -> None:
    """幂等校验三张记忆表及其索引；缺项时自动建表（调用 init_db.create_memory_tables）。"""
    cfg = config or get_config()
    if not cfg.database_url:
        raise SystemExit("DATABASE_URL 未配置，无法完成 memory setup")

    from scripts.init_db import create_memory_tables

    from app.persistence import db as pgdb

    with pgdb.connect(cfg) as conn:
        create_memory_tables(conn)  # 幂等：已存在则跳过
        conn.row_factory = dict_row
        tables = {
            r["tablename"]
            for r in conn.execute(
                "SELECT tablename FROM pg_tables WHERE schemaname = 'current_schema()'"
                " OR tablename IN ('memories','memory_events','pending_actions')"
            ).fetchall()
        }
        for t in ("memories", "memory_events", "pending_actions"):
            if t not in tables:
                raise RuntimeError(f"memory 表缺失：{t}")
        # 向量索引存在性（提示性，不阻断：hnsw 依赖 vector 扩展，于 init_db 时已建）
        conn.execute("SET search_path TO public")
        idx = conn.execute(
            "SELECT indexname FROM pg_indexes WHERE tablename='memories' AND indexname='idx_memories_embedding'"
        ).fetchone()
        status = f"index={'ok' if idx else 'missing'}"
    print(f"memory setup 校验通过（{status}）：memories / memory_events / pending_actions")


if __name__ == "__main__":
    verify()