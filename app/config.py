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

    @property
    def llm_enabled(self) -> bool:
        return bool(self.llm_api_key)


_config: Config | None = None


def get_config() -> Config:
    """返回全局默认配置（读取环境变量）。"""
    global _config
    if _config is None:
        _config = Config()
    return _config
