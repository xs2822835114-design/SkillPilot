"""初始化数据库：创建 database（若不存在）与 users/threads 表（幂等）。

仅应在应用启动/迁移阶段执行一次：
    .venv/bin/python -m scripts.init_db
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import psycopg

from app.config import get_config


def _db_name(database_url: str) -> str:
    _, rest = database_url.split("://", 1)
    return rest.rsplit("/", 1)[-1]


def _admin_dsn(database_url: str) -> str:
    """将连接串指向管理库（postgres），以便创建目标库。"""
    scheme, rest = database_url.split("://", 1)
    host_part = rest.rsplit("/", 1)[0]
    return f"{scheme}://{host_part}/postgres"


def create_tables(conn) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id          VARCHAR(64) PRIMARY KEY,
            name        VARCHAR(128),
            target_role VARCHAR(64),
            created_at  TIMESTAMPTZ DEFAULT now()
        );
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS threads (
            thread_id       VARCHAR(64) PRIMARY KEY,
            user_id         VARCHAR(64) NOT NULL,
            title           VARCHAR(255),
            created_at      TIMESTAMPTZ DEFAULT now(),
            last_message_at TIMESTAMPTZ DEFAULT now()
        );
        """
    )
    print("users / threads 表已就绪")


def create_rag_tables(conn) -> None:
    """阶段 2：启用 pgvector 扩展并创建 RAG 知识库表与索引（幂等）。

    注：vector 扩展需超管在服务器上安装（CREATE EXTENSION vector）。当前连接用户
    可能无建扩展权限，若扩展已存在则跳过，不影响后续建表与向量列使用。
    """
    try:
        conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
    except psycopg.errors.InsufficientPrivilege:  # noqa: PERF203
        print("提示：vector 扩展已由超管创建（当前用户无建扩展权限），跳过")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS rag_documents (
          doc_id      VARCHAR(64) PRIMARY KEY,
          title       VARCHAR(255),
          source      TEXT,
          source_type VARCHAR(32) DEFAULT 'text',
          category    VARCHAR(64),
          lang        VARCHAR(16) DEFAULT 'zh',
          role_target VARCHAR(64),
          skill_tags  TEXT[],
          meta        JSONB DEFAULT '{}',
          created_at  TIMESTAMPTZ DEFAULT now(),
          updated_at  TIMESTAMPTZ DEFAULT now()
        );
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS rag_chunks (
          chunk_id    VARCHAR(64) PRIMARY KEY,
          doc_id      VARCHAR(64) NOT NULL REFERENCES rag_documents(doc_id) ON DELETE CASCADE,
          chunk_index INTEGER NOT NULL,
          content     TEXT NOT NULL,
          token_count INTEGER DEFAULT 0,
          embedding   vector(1024),
          created_at  TIMESTAMPTZ DEFAULT now()
        );
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_rag_chunks_embedding
          ON rag_chunks USING hnsw (embedding vector_cosine_ops)
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_rag_documents_category ON rag_documents(category)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_rag_chunks_doc ON rag_chunks(doc_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_rag_documents_source ON rag_documents(source)")
    print("rag_documents / rag_chunks 表与索引已就绪")


def create_profile_tables(conn) -> None:
    """阶段 3：用户技术画像相关表（技能字典/画像/项目/偏好/证据，幂等）。"""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS skills (
          id          VARCHAR(64) PRIMARY KEY,
          name        VARCHAR(128) NOT NULL,
          category    VARCHAR(64),
          description TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_skills_name ON skills(name);
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS user_skills (
          user_id        VARCHAR(64) NOT NULL,
          skill_id       VARCHAR(64) NOT NULL REFERENCES skills(id),
          theory_score   SMALLINT NOT NULL DEFAULT 0,
          practice_score SMALLINT NOT NULL DEFAULT 0,
          confidence     REAL NOT NULL DEFAULT 0,
          last_proven_at TIMESTAMPTZ,
          updated_at     TIMESTAMPTZ DEFAULT now(),
          PRIMARY KEY (user_id, skill_id)
        );
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS projects (
          id          VARCHAR(64) PRIMARY KEY,
          user_id     VARCHAR(64) NOT NULL,
          name        VARCHAR(255),
          description TEXT,
          repo_url    TEXT,
          skills      TEXT[] DEFAULT '{}',
          created_at  TIMESTAMPTZ DEFAULT now()
        );
        CREATE INDEX IF NOT EXISTS idx_projects_user ON projects(user_id);
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS user_preferences (
          user_id    VARCHAR(64) NOT NULL,
          key        VARCHAR(64) NOT NULL,
          value      JSONB,
          updated_at TIMESTAMPTZ DEFAULT now(),
          PRIMARY KEY (user_id, key)
        );
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS skill_evidence (
          id           VARCHAR(64) PRIMARY KEY,
          user_id      VARCHAR(64) NOT NULL,
          source_type  VARCHAR(32),
          source_ref   VARCHAR(255),
          claim        TEXT,
          extracted_at TIMESTAMPTZ DEFAULT now()
        );
        CREATE INDEX IF NOT EXISTS idx_skill_evidence_user ON skill_evidence(user_id);
        """
    )
    print("skills / user_skills / projects / user_preferences / skill_evidence 表已就绪")


def create_gap_tables(conn) -> None:
    """阶段 4：Skill Graph 相关表（技能图节点/边/岗位要求，幂等）。"""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS skill_nodes (
          id          VARCHAR(64) PRIMARY KEY,
          name        VARCHAR(128) NOT NULL,
          domain      VARCHAR(64),
          description TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_skill_nodes_name ON skill_nodes(name);
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS skill_edges (
          source VARCHAR(64) NOT NULL REFERENCES skill_nodes(id),
          target VARCHAR(64) NOT NULL REFERENCES skill_nodes(id),
          rel    VARCHAR(32) NOT NULL,
          PRIMARY KEY (source, target, rel)
        );
        CREATE INDEX IF NOT EXISTS idx_skill_edges_rel ON skill_edges(rel);
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS role_skills (
          role_id   VARCHAR(64) NOT NULL,
          role_name VARCHAR(128),
          category  VARCHAR(64),
          skill_id  VARCHAR(64) NOT NULL REFERENCES skill_nodes(id),
          level     SMALLINT NOT NULL,
          weight    REAL NOT NULL DEFAULT 1.0,
          reason    VARCHAR(255),
          PRIMARY KEY (role_id, skill_id)
        );
        CREATE INDEX IF NOT EXISTS idx_role_skills_role ON role_skills(role_id);
        """
    )
    print("skill_nodes / skill_edges / role_skills 表已就绪")


def create_todo_tables(conn) -> None:
    """阶段 5：学习计划与任务相关表（计划/任务，幂等）。"""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS learning_plans (
          id           VARCHAR(64) PRIMARY KEY,
          user_id      VARCHAR(64) NOT NULL,
          goal         VARCHAR(255),
          source_role  VARCHAR(64),
          status       VARCHAR(24) NOT NULL DEFAULT 'in_progress',
          skill_ids    JSONB,
          report_json  JSONB,
          metrics_json JSONB,
          is_llm_enhanced BOOLEAN NOT NULL DEFAULT false,
          created_at   TIMESTAMPTZ DEFAULT now(),
          updated_at   TIMESTAMPTZ DEFAULT now()
        );
        CREATE INDEX IF NOT EXISTS idx_learning_plans_user ON learning_plans(user_id);
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS learning_tasks (
          id                 VARCHAR(64) PRIMARY KEY,
          plan_id            VARCHAR(64) NOT NULL REFERENCES learning_plans(id) ON DELETE CASCADE,
          phase_id           VARCHAR(64) NOT NULL,
          phase_order        SMALLINT NOT NULL,
          task_order         SMALLINT NOT NULL,
          skill_id           VARCHAR(64),
          title              VARCHAR(255),
          estimated_hours    REAL NOT NULL DEFAULT 4,
          status             VARCHAR(24) NOT NULL DEFAULT 'pending',
          acceptance_criteria TEXT,
          resources_json     JSONB,
          steps_json         JSONB,
          execution_steps_json JSONB,
          is_refined         BOOLEAN NOT NULL DEFAULT false,
          required           BOOLEAN NOT NULL DEFAULT false,
          started_at         TIMESTAMPTZ,
          finished_at        TIMESTAMPTZ,
          created_at         TIMESTAMPTZ DEFAULT now(),
          updated_at         TIMESTAMPTZ DEFAULT now()
        );
        CREATE INDEX IF NOT EXISTS idx_learning_tasks_plan
          ON learning_tasks(plan_id, phase_order, task_order);
        """
    )
    # 既有库补齐步骤明细列（幂等；新库已在建表语句内创建）
    conn.execute("ALTER TABLE learning_tasks ADD COLUMN IF NOT EXISTS steps_json JSONB")
    conn.execute("ALTER TABLE learning_tasks ADD COLUMN IF NOT EXISTS execution_steps_json JSONB")
    conn.execute("ALTER TABLE learning_tasks ADD COLUMN IF NOT EXISTS is_refined BOOLEAN DEFAULT false")
    print("learning_plans / learning_tasks 表已就绪")


def create_eval_tables(conn) -> None:
    """阶段 6：实践任务与能力评估表（实践/评估/代码片段，幂等）。"""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS practices (
          id           VARCHAR(64) PRIMARY KEY,
          plan_id      VARCHAR(64),
          task_id      VARCHAR(64),
          user_id      VARCHAR(64) NOT NULL,
          skill_id     VARCHAR(64),
          format       VARCHAR(24) NOT NULL DEFAULT 'project',
          level_target SMALLINT NOT NULL DEFAULT 1,
          deliverables_json JSONB,
          rubric_json   JSONB,
          status       VARCHAR(24) NOT NULL DEFAULT 'pending',
          is_llm_enhanced BOOLEAN NOT NULL DEFAULT false,
          created_at   TIMESTAMPTZ DEFAULT now()
        );
        CREATE INDEX IF NOT EXISTS idx_practices_user ON practices(user_id);
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS evaluations (
          id            VARCHAR(64) PRIMARY KEY,
          practice_id   VARCHAR(64),
          user_id       VARCHAR(64) NOT NULL,
          artifact_type VARCHAR(24) NOT NULL DEFAULT 'snippet',
          artifact_ref  TEXT,
          skill_id      VARCHAR(64),
          overall_score SMALLINT,
          report_json   JSONB,
          profile_updated BOOLEAN NOT NULL DEFAULT false,
          replanned       BOOLEAN NOT NULL DEFAULT false,
          created_at    TIMESTAMPTZ DEFAULT now()
        );
        CREATE INDEX IF NOT EXISTS idx_evaluations_user ON evaluations(user_id);
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS code_snippets (
          id           VARCHAR(64) PRIMARY KEY,
          user_id      VARCHAR(64) NOT NULL,
          practice_id  VARCHAR(64),
          language     VARCHAR(24) NOT NULL DEFAULT 'python',
          filename     VARCHAR(255),
          content      TEXT,
          created_at   TIMESTAMPTZ DEFAULT now()
        );
        CREATE INDEX IF NOT EXISTS idx_code_snippets_user ON code_snippets(user_id);
        """
    )
    print("practices / evaluations / code_snippets 表已就绪")


def create_memory_tables(conn) -> None:
    """阶段 7 长期记忆：memories / memory_events / pending_actions（幂等，物理索引对齐阶段2 1024 维）。"""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS memories (
          id         VARCHAR(64) PRIMARY KEY,
          user_id    VARCHAR(64) NOT NULL,
          namespace  VARCHAR(24) NOT NULL,
          key        VARCHAR(96) NOT NULL,
          text       TEXT,
          payload    JSONB,
          embedding  vector(1024),
          importance REAL DEFAULT 0,
          created_at TIMESTAMPTZ DEFAULT now(),
          updated_at TIMESTAMPTZ DEFAULT now(),
          UNIQUE (user_id, namespace, key)
        );
        CREATE INDEX IF NOT EXISTS idx_memories_user_namespace ON memories(user_id, namespace);
        CREATE INDEX IF NOT EXISTS idx_memories_key ON memories(key);
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_memories_embedding
          ON memories USING hnsw (embedding vector_cosine_ops)
          WHERE embedding IS NOT NULL
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS memory_events (
          id         VARCHAR(64) PRIMARY KEY,
          user_id    VARCHAR(64) NOT NULL,
          event_type VARCHAR(32) NOT NULL,
          ref_ids    JSONB,
          summary    TEXT,
          payload    JSONB,
          created_at TIMESTAMPTZ DEFAULT now()
        );
        CREATE INDEX IF NOT EXISTS idx_memory_events_user_type ON memory_events(user_id, event_type);
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS pending_actions (
          id           VARCHAR(64) PRIMARY KEY,
          user_id      VARCHAR(64) NOT NULL,
          action_type  VARCHAR(32) NOT NULL,
          payload      JSONB,
          status       VARCHAR(16) NOT NULL DEFAULT 'pending',
          summary      TEXT,
          requested_at TIMESTAMPTZ DEFAULT now(),
          decided_at   TIMESTAMPTZ
        );
        CREATE INDEX IF NOT EXISTS idx_pending_actions_user_status ON pending_actions(user_id, status);
        """
    )
    print("memories / memory_events / pending_actions 表已就绪")


def create_interview_tables(conn) -> None:
    """阶段 10：AI 问答式能力评估表（会话/逐题答案，幂等）。"""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS interview_sessions (
          id             TEXT PRIMARY KEY,
          user_id        TEXT NOT NULL,
          skill_id       TEXT NOT NULL,
          skill_name     TEXT,
          status         TEXT NOT NULL DEFAULT 'in_progress',
          current_index  INT NOT NULL DEFAULT 0,
          questions_json JSONB NOT NULL DEFAULT '[]',
          scores_json    JSONB,
          created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
          finished_at    TIMESTAMPTZ
        );
        CREATE INDEX IF NOT EXISTS idx_interview_sessions_user
          ON interview_sessions(user_id);
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS interview_answers (
          id         TEXT PRIMARY KEY,
          session_id TEXT NOT NULL REFERENCES interview_sessions(id) ON DELETE CASCADE,
          q_index    INT NOT NULL,
          question   TEXT,
          answer     TEXT,
          score      INT,
          feedback   TEXT,
          created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
          UNIQUE (session_id, q_index)
        );
        CREATE INDEX IF NOT EXISTS idx_interview_answers_session
          ON interview_answers(session_id);
        """
    )
    print("interview_sessions / interview_answers 表已就绪")


def create_teaching_tables(conn) -> None:
    """阶段 5b：AI 教学会话与回合表（user_id + task_id 唯一定位学习会话，支持恢复，幂等）。"""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS teaching_sessions (
          session_id          VARCHAR(64) PRIMARY KEY,
          user_id             VARCHAR(64) NOT NULL,
          plan_id             VARCHAR(64) NOT NULL,
          task_id             VARCHAR(64) NOT NULL,
          title               TEXT,
          learning_objective  TEXT,
          acceptance_criteria TEXT,
          opening             TEXT,
          content_json        JSONB,
          status              VARCHAR(24) NOT NULL DEFAULT 'active',
          current_step        INT NOT NULL DEFAULT 0,
          created_at          TIMESTAMPTZ DEFAULT now(),
          updated_at          TIMESTAMPTZ DEFAULT now()
        );
        CREATE INDEX IF NOT EXISTS idx_teaching_sessions_user_task
          ON teaching_sessions(user_id, task_id);
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS teaching_turns (
          id            SERIAL PRIMARY KEY,
          session_id    VARCHAR(64) NOT NULL
                        REFERENCES teaching_sessions(session_id) ON DELETE CASCADE,
          role          VARCHAR(10) NOT NULL,
          message       TEXT,
          mode          VARCHAR(24),
          content_json  JSONB,
          created_at    TIMESTAMPTZ DEFAULT now()
        );
        CREATE INDEX IF NOT EXISTS idx_teaching_turns_session
          ON teaching_turns(session_id);
        """
    )
    print("teaching_sessions / teaching_turns 表已就绪")


def run() -> None:
    cfg = get_config()
    if not cfg.database_url:
        raise SystemExit("DATABASE_URL 未配置，无法初始化数据库")

    target = cfg.database_url
    dbname = _db_name(target)

    # 1) 确保目标库存在
    with psycopg.connect(_admin_dsn(target), autocommit=True) as conn:
        exists = conn.execute(
            "SELECT 1 FROM pg_database WHERE datname = %s", (dbname,)
        ).fetchone()
        if not exists:
            conn.execute(f'CREATE DATABASE "{dbname}"')
            print(f"已创建数据库 {dbname}")

    # 2) 连接目标库建表
    with psycopg.connect(target, autocommit=True) as conn:
        create_tables(conn)
        create_rag_tables(conn)
        create_profile_tables(conn)
        create_gap_tables(conn)
        create_todo_tables(conn)
        create_eval_tables(conn)
        create_memory_tables(conn)
        create_interview_tables(conn)
        create_teaching_tables(conn)

    print("数据库初始化完成")


if __name__ == "__main__":
    run()
