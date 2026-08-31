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

    这是「Skill Resolver」：只负责把用户明确提到的目标**规范化**到技能库里的标准 id。
    它判断的是「系统认不认识这个技能」，而不是「用户到底想学什么」。

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


# ---------------- 「理解用户想学什么」（独立于技能库） ----------------

# 学习动词簇（顺序无关，.search 取最左命中）
_LEARN_VERB = (
    r"(?:想系统学习|准备学习|准备学|想学习|想入门|要学习|想掌握|想学|要学|"
    r"打算学|学一下|学一学|自学|入门|掌握|学会|学习)"
)
# 句式 A：动词 + 可选量词 + 目标。
#   拉丁分支净取词：遇到非字母字符即停，天然处理「PHP」「Python」「C++」「Spring Boot」，
#   也把「PHP语言」「Python后端」切成干净词根；中文分支负责「微积分」这类纯中文目标。
_AFTER_VERB_RE = re.compile(
    rf"{_LEARN_VERB}\s*(?:一门|一个|一下|点|亿点)?\s*"
    r"(?P<skill>[A-Za-z][\w+#.]*(?:\s+[A-Za-z][\w+#.]*)?|[\u4e00-\u9fa5]{2,20})",
    re.UNICODE,
)
# 句式 B：目标在前（如「PHP 怎么学」「Rust 从零学」「卡尔曼滤波如何上手」）。
#   仅在「无前置学习动词」时才适用——避免「我想学」被误判成技能"我想"。
_TARGET_FIRST_RE = re.compile(
    r"^\s*(?P<skill>[A-Za-z][\w+#.]*|[\u4e00-\u9fa5]{2,20})\s*"
    r"(?:怎么|如何|从零|怎么系统|要)?\s*(?:学|入门|学习|掌握|上手|突破)",
    re.UNICODE,
)
# 只要消息含学习动词，就不再用「目标在前」句式（防止「我想学」空目标被误抓）
_LEARN_VERB_RE = re.compile(_LEARN_VERB, re.UNICODE)
# 通用「领域/体裁」尾缀：剥离后得到更干净的目标词根（PHP语言→PHP、前端开发→前端）
_TRAILING_GENRE = ("语言", "后端", "前端", "开发", "框架", "技术", "编程", "程序设计", "领域", "方向")


def _clean_target_name(name: str) -> str:
    """去掉用法/体裁类尾缀，得到一个可作目标名的干净词根。"""
    n = (name or "").strip()
    if not n:
        return ""
    for suf in _TRAILING_GENRE:
        if n.endswith(suf) and len(n) > len(suf):
            return n[: -len(suf)].strip()
    return n


def _coerce_target_names(raw) -> list[str]:
    """把 LLM 结构化输出里的 target_skills（str 或 dict）规整成干净名称列表。"""
    if not raw:
        return []
    out: list[str] = []
    for x in raw:
        if isinstance(x, dict):
            x = x.get("skill_name") or x.get("skill_id") or x.get("target")
        if isinstance(x, str):
            c = _clean_target_name(x)
            if c and c not in out:
                out.append(c)
    return out


def _extract_target_names(message: str) -> list[str]:
    """从 tech_learning 消息里泛化提取用户想学的东西（技能名），不依赖技能库。

    只做「理解用户想学什么」的语法层提取：去掉学习动词、量词、常见尾缀，得到一个可作
    目标名的候选。技能是否存在于知识库等规范性判断交给 Skill Resolver（_resolve_skill）。
    找不到明确目标返回空列表（由调用方追问），但绝不把「库中没有」误判为「用户没说要学什么」。
    """
    text = (message or "").strip()
    if not text:
        return []
    m = _AFTER_VERB_RE.search(text)
    if m:
        cleaned = _clean_target_name(m.group("skill") or "")
        return [cleaned] if cleaned else []
    # 无前置学习动词（如「PHP 怎么学」）才走「目标在前」句式，
    # 避免「我想学」这类空目标被误抓成技能名。
    if not _LEARN_VERB_RE.search(text):
        m = _TARGET_FIRST_RE.search(text)
        if m:
            cleaned = _clean_target_name(m.group("skill") or "")
            if cleaned:
                return [cleaned]
    return []


def parse(
    config: Config,
    message: str,
    intent: str,
    llm_targets: list | None = None,
) -> dict[str, Any]:
    """解析意图入参（确定性规则）。

    ``llm_targets``：Orchestrator 的 LLM 结构化输出里提取出的目标技能名（如 ["PHP"]）。
    职责分离：LLM/规则负责「理解用户想学什么」，Skill Resolver（_resolve_skill）负责
    「把目标规范化到技能库」，两者不再耦合。
    """
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
        # 技术学习：Skill Resolver 先查技能库；
        # 库中命中 → 用标准 skill_id；库中未命中 → 保留用户原始目标（unknown），
        # 绝不把「库中没有」误判为「用户没说要学什么」。
        skill = _resolve_skill(config, message)
        if skill:
            params.target_skills = [
                {"skill_id": skill["id"], "skill_name": skill["name"], "level": 3, "weight": 1.0}
            ]
        else:
            names = _coerce_target_names(llm_targets) or _extract_target_names(message)
            if names:
                params.target_skills = [
                    {"skill_id": n, "skill_name": n, "level": 3, "weight": 1.0, "unknown": True}
                    for n in names
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