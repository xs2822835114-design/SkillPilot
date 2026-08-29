"""意图 → 结构化请求参数解析（多 Agent 路由）。

精简后仅支持 plan_generation 与 chat 两条主线。

设计：
- 规则优先、确定性可重复（LLM 增强可选，默认关闭）；
- 目标岗位解析：DB 可读时用 role_skills 真实岗位，否则用内置常用岗位表；
- 想学某技能时解析 skill_id，由 plan_node 反查技能所属岗位；
- 解析失败不硬猜：缺入参时置 `unanswered`，由 reply_node 向用户追问可选值。
"""
from __future__ import annotations

import logging
import re
from typing import Any

from pydantic import BaseModel, Field

from app.config import Config

logger = logging.getLogger(__name__)

# 内置常用岗位表（DB 不可用/未建表时的兜底，与 SkillPilot_role_competencies.json 的 role_id 一致）
_BUILTIN_ROLES: list[dict[str, str]] = [
    {"role_id": "RC001", "role_name": "AI 应用工程师"},
    {"role_id": "RC002", "role_name": "AI Agent 工程师"},
    {"role_id": "RC003", "role_name": "大模型应用工程师（RAG/知识库）"},
    {"role_id": "RC004", "role_name": "大模型算法工程师"},
    {"role_id": "RC005", "role_name": "机器学习工程师"},
    {"role_id": "RC008", "role_name": "数据分析师"},
    {"role_id": "RC010", "role_name": "Java 后端工程师"},
    {"role_id": "RC011", "role_name": "Go 后端工程师"},
    {"role_id": "RC012", "role_name": "Node.js 后端工程师"},
    {"role_id": "RC013", "role_name": "Python 后端工程师"},
    {"role_id": "RC014", "role_name": "后端架构师"},
    {"role_id": "RC015", "role_name": "前端工程师"},
    {"role_id": "RC016", "role_name": "全栈工程师"},
    {"role_id": "RC017", "role_name": "数据库工程师（DBA）"},
    {"role_id": "RC020", "role_name": "DevOps 工程师"},
    {"role_id": "RC021", "role_name": "SRE 工程师"},
    {"role_id": "RC024", "role_name": "测试开发工程师"},
    {"role_id": "RC027", "role_name": "软件研发工程师（通用）"},
    {"role_id": "RC029", "role_name": "云原生工程师"},
]

# 关键词别名 → role_id（长别名优先，避免"算法"等短词误配）
_ROLE_ALIASES: dict[str, str] = {
    "ai应用工程师": "RC001",
    "ai应用": "RC001",
    "aiagent工程师": "RC002",
    "ai agent工程师": "RC002",
    "agent工程师": "RC002",
    "智能体工程师": "RC002",
    "rag工程师": "RC003",
    "知识库工程师": "RC003",
    "大模型应用": "RC003",
    "算法工程师": "RC004",
    "机器学习工程师": "RC005",
    "机器学习": "RC005",
    "数据分析": "RC008",
    "java后端": "RC010",
    "java工程师": "RC010",
    "go后端": "RC011",
    "go工程师": "RC011",
    "node工程师": "RC012",
    "nodejs": "RC012",
    "python后端": "RC013",
    "python工程师": "RC013",
    "后端架构": "RC014",
    "架构师": "RC014",
    "前端工程师": "RC015",
    "前端": "RC015",
    "全栈": "RC016",
    "数据库工程师": "RC017",
    "dba": "RC017",
    "devops": "RC020",
    "运维工程师": "RC020",
    "sre": "RC021",
    "测试开发": "RC024",
    "云原生": "RC029",
}


class IntentParams(BaseModel):
    """路由节点消费的结构化入参。unanswered 非空表示需要用户补充信息（追问）。"""

    intent: str = "chat"
    target_roles: list[str] = Field(default_factory=list)     # plan/job 用（目标岗位 role_id）
    target_skills: list[dict] = Field(default_factory=list)   # tech 用（[{"skill_id","skill_name","level","weight"}）
    skill_id: str | None = None                                # plan 用（想学的技能）
    unanswered: list[str] = Field(default_factory=list)        # 缺哪些入参

    def need(self, key: str) -> None:
        if key not in self.unanswered:
            self.unanswered.append(key)


def _normalize(text: str) -> str:
    """归一化：去空白/括号/常见标点，转小写，用于岗位匹配。"""
    text = (text or "").lower()
    text = re.sub(r"[（）()\[\]【】、，,。.；;：:\s/\\-]", "", text)
    return text


def _load_role_catalog(config: Config) -> list[dict[str, str]]:
    """读取真实岗位（role_skills）；失败/未配置 DB 时用内置表。"""
    if config.database_url:
        try:
            from psycopg.rows import dict_row

            from app.persistence import db as pgdb

            with pgdb.connect(config) as conn:
                conn.row_factory = dict_row
                rows = conn.execute(
                    "SELECT DISTINCT role_id, role_name FROM role_skills WHERE role_name IS NOT NULL"
                ).fetchall()
            if rows:
                return [{"role_id": r["role_id"], "role_name": r["role_name"]} for r in rows]
        except Exception:  # noqa: BLE001
            logger.warning("读取岗位目录失败，使用内置表", exc_info=True)
    return list(_BUILTIN_ROLES)


def _resolve_target_roles(config: Config, message: str) -> list[str]:
    """从消息解析目标岗位 role_id（最长匹配优先）。无命中返回空列表。"""
    norm = _normalize(message)
    if not norm:
        return []

    candidates: dict[str, int] = {}  # role_id -> matched_len

    # 1) 关键词别名（长别名优先）
    for alias, role_id in _ROLE_ALIASES.items():
        key = _normalize(alias)
        if key and key in norm:
            candidates[role_id] = max(candidates.get(role_id, 0), len(key))

    # 2) 岗位全名包含匹配
    for role in _load_role_catalog(config):
        key = _normalize(role["role_name"])
        if key and key in norm:
            candidates[role["role_id"]] = max(candidates.get(role["role_id"], 0), len(key))

    if not candidates:
        return []
    best = max(candidates.items(), key=lambda kv: (kv[1], kv[0]))
    return [best[0]]


def _resolve_skill(config: Config, message: str) -> dict | None:
    """从消息中匹配技能词典（JSON/DB 均可用），返回 ``{id, name, domain}``。

    最长匹配优先，避免「SQL」误配「SQLite」这类短词；读取失败返回 None。
    """
    norm = _normalize(message)
    if not norm:
        return None
    try:
        from app.knowledge import list_skills

        skills = list_skills(config)
    except Exception:  # noqa: BLE001
        logger.warning("读取技能词典失败，无法解析目标技能", exc_info=True)
        return None
    best: dict | None = None
    best_len = 0
    for sk in skills:
        key = _normalize(str(sk.get("name") or ""))
        if not key or len(key) <= best_len:
            continue
        if key in norm:
            best = sk
            best_len = len(key)
    return best


def _resolve_skill_id(config: Config, message: str) -> str | None:
    """从消息中匹配技能名，返回规范 id（供 plan_generation 反查技能所属岗位）。"""
    sk = _resolve_skill(config, message)
    return sk["id"] if sk else None


def parse(config: Config, message: str, intent: str) -> dict[str, Any]:
    """解析意图入参（确定性规则）。"""
    params = IntentParams(intent=intent)

    if intent == "plan_generation":
        # 学习计划既可按「目标岗位」，也可按「想学的技能」推进：
        # - 岗位直接给出 → 用岗位；
        # - 只给了技能名（如 Flask）→ 解析出 skill_id，由 plan_node 反查技能所属岗位；
        # - 都没有 → 追问（可选值里同时提示技能）。
        roles = _resolve_target_roles(config, message)
        if roles:
            params.target_roles = roles
        skill_id = _resolve_skill_id(config, message)
        if skill_id:
            params.skill_id = skill_id
        if not roles and not skill_id:
            params.need("target_roles")

    elif intent == "tech_learning":
        # 技术学习：从消息解析目标技能（如「我想学 LangGraph」→ langgraph）。
        skill = _resolve_skill(config, message)
        if skill:
            params.target_skills = [
                {"skill_id": skill["id"], "skill_name": skill["name"], "level": 3, "weight": 1.0}
            ]
        else:
            params.need("target_skills")

    elif intent == "job_search":
        # 岗位求职：从消息解析目标岗位（如「我想找 AI Agent 工程师」→ RC002）。
        roles = _resolve_target_roles(config, message)
        if roles:
            params.target_roles = roles
        else:
            params.need("target_roles")

    return params.model_dump(mode="json")


def list_skill_names(config: Config, limit: int = 6) -> str:
    """追问时列出可选技能（供回复使用）。"""
    try:
        from app.profile import store as profile_store

        names = [r["name"] for r in profile_store.load_skill_names(config)]
    except Exception:  # noqa: BLE001
        return "（暂无技能数据）"
    return "、".join(names[:limit]) or "（暂无技能数据）"


def list_role_names(config: Config, limit: int = 5) -> str:
    """追问时列出可选岗位（供回复使用）。"""
    roles = _load_role_catalog(config)[:limit]
    return "、".join(r["role_name"] for r in roles) or "（暂无岗位数据）"