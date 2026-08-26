"""配置管理：环境变量加载与 Config 对象。"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent

# 加载项目根目录的 .env（若存在）
load_dotenv(BASE_DIR / ".env")


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, default))
    except (TypeError, ValueError):
        return default


@dataclass
class Config:
    env: str = field(default_factory=lambda: os.getenv("ENV", "dev"))
    version: str = "v1.0.0"
    database_url: str = field(default_factory=lambda: os.getenv("DATABASE_URL", ""))
    llm_api_key: str = field(default_factory=lambda: os.getenv("LLM_API_KEY", ""))
    llm_model: str = field(default_factory=lambda: os.getenv("LLM_MODEL", "deepseek-v4-flash"))
    # OpenAI 兼容端点（DeepSeek 默认 https://api.deepseek.com）
    llm_base_url: str = field(default_factory=lambda: os.getenv("LLM_BASE_URL", "https://api.deepseek.com"))
    log_level: str = field(default_factory=lambda: os.getenv("LOG_LEVEL", "INFO"))
    message_max_len: int = field(default_factory=lambda: _env_int("MESSAGE_MAX_LEN", 8000))
    max_attachments: int = field(default_factory=lambda: _env_int("MAX_ATTACHMENTS", 5))
    # checkpointer 后端：auto | postgres | memory
    checkpointer_backend: str = field(default_factory=lambda: os.getenv("CHECKPOINTER_BACKEND", "auto"))
    # ---------- 阶段 2 RAG / Embedding ----------
    embedding_provider: str = field(default_factory=lambda: os.getenv("EMBEDDING_PROVIDER", "off"))
    embedding_base_url: str = field(
        default_factory=lambda: os.getenv("EMBEDDING_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1")
    )
    embedding_api_key: str = field(default_factory=lambda: os.getenv("EMBEDDING_API_KEY", ""))
    embedding_model: str = field(default_factory=lambda: os.getenv("EMBEDDING_MODEL", "qwen3.7-text-embedding"))
    embedding_dim: int = field(default_factory=lambda: _env_int("EMBEDDING_DIM", 1024))
    rag_top_k_default: int = field(default_factory=lambda: _env_int("RAG_TOP_K_DEFAULT", 5))
    rag_chunk_size: int = field(default_factory=lambda: _env_int("RAG_CHUNK_SIZE", 800))
    rag_chunk_overlap: int = field(default_factory=lambda: _env_int("RAG_CHUNK_OVERLAP", 100))
    # ---------- 阶段 3 用户技术画像 ----------
    profile_practice_weight: float = field(default_factory=lambda: float(os.getenv("PROFILE_PRACTICE_WEIGHT", "0.6")))
    profile_soft_cap_skills: int = field(default_factory=lambda: _env_int("PROFILE_SOFT_CAP_SKILLS", 30))
    profile_min_confidence: float = field(default_factory=lambda: float(os.getenv("PROFILE_MIN_CONFIDENCE", "0.4")))
    profile_llm_enabled: bool = field(default_factory=lambda: os.getenv("PROFILE_LLM_ENABLED", "true").lower() == "true")
    # ---------- 阶段 4 Skill Graph / Gap ----------
    gap_top_default: int = field(default_factory=lambda: _env_int("GAP_TOP_DEFAULT", 50))
    gap_prereq_decay: float = field(default_factory=lambda: float(os.getenv("GAP_PREREQ_DECAY", "0.5")))
    gap_llm_enabled: bool = field(default_factory=lambda: os.getenv("GAP_LLM_ENABLED", "true").lower() == "true")
    # ---------- 阶段 5 学习规划 / Todo ----------
    plan_default_weekly_hours: int = field(default_factory=lambda: _env_int("PLAN_DEFAULT_WEEKLY_HOURS", 5))
    plan_phases_cap: int = field(default_factory=lambda: _env_int("PLAN_PHASES_CAP", 8))
    plan_min_task_hours: float = field(default_factory=lambda: float(os.getenv("PLAN_MIN_TASK_HOURS", "2")))
    plan_max_task_hours: float = field(default_factory=lambda: float(os.getenv("PLAN_MAX_TASK_HOURS", "12")))
    plan_hours_per_level: float = field(default_factory=lambda: float(os.getenv("PLAN_HOURS_PER_LEVEL", "3")))
    plan_llm_enabled: bool = field(default_factory=lambda: os.getenv("PLAN_LLM_ENABLED", "true").lower() == "true")
    # ---------- 阶段 6 实践任务与能力评估 ----------
    eval_static_strict: bool = field(default_factory=lambda: os.getenv("EVAL_STATIC_STRICT", "true").lower() == "true")
    eval_theory_weight: float = field(default_factory=lambda: float(os.getenv("EVAL_THEORY_WEIGHT", "0.4")))
    eval_trigger_replan_default: bool = field(default_factory=lambda: os.getenv("EVAL_TRIGGER_REPLAN_DEFAULT", "true").lower() == "true")
    eval_llm_enabled: bool = field(default_factory=lambda: os.getenv("EVAL_LLM_ENABLED", "true").lower() == "true")
    practice_default_level_target: int = field(default_factory=lambda: _env_int("PRACTICE_DEFAULT_LEVEL_TARGET", 3))
    practice_llm_enabled: bool = field(default_factory=lambda: os.getenv("PRACTICE_LLM_ENABLED", "true").lower() == "true")
    # ---------- 阶段 7 长期记忆与 Middleware ----------
    memory_enabled: bool = field(default_factory=lambda: os.getenv("MEMORY_ENABLED", "true").lower() == "true")
    memory_embed_enabled: bool = field(default_factory=lambda: os.getenv("MEMORY_EMBED_ENABLED", "true").lower() == "true")
    memory_top_k: int = field(default_factory=lambda: _env_int("MEMORY_TOP_K", 5))
    memory_summary_threshold_messages: int = field(default_factory=lambda: _env_int("MEMORY_SUMMARY_THRESHOLD_MESSAGES", 20))
    memory_summary_llm_enabled: bool = field(default_factory=lambda: os.getenv("MEMORY_SUMMARY_LLM_ENABLED", "true").lower() == "true")
    memory_pii_enabled: bool = field(default_factory=lambda: os.getenv("MEMORY_PII_ENABLED", "true").lower() == "true")
    memory_hitl_enabled: bool = field(default_factory=lambda: os.getenv("MEMORY_HITL_ENABLED", "true").lower() == "true")
    memory_hitl_expires_seconds: int = field(default_factory=lambda: _env_int("MEMORY_HITL_EXPIRES_SECONDS", 86400))
    # ---------- 阶段 8 前端整合与 Demo ----------
    demo_user_id: str = field(default_factory=lambda: os.getenv("DEMO_USER_ID", "demo_user"))
    stream_enabled: bool = field(default_factory=lambda: os.getenv("STREAM_ENABLED", "true").lower() == "true")

    @property
    def llm_enabled(self) -> bool:
        return bool(self.llm_api_key)

    @property
    def embedding_enabled(self) -> bool:
        return self.embedding_provider == "openai" and bool(self.embedding_api_key)


_config: Config | None = None


def get_config() -> Config:
    """返回全局默认配置（读取环境变量）。"""
    global _config
    if _config is None:
        _config = Config()
    return _config
