"""生成技能图种子（阶段 4）：由阶段 2 两份 JSON 生成 skill_nodes/skill_edges/role_skills（幂等 + dry-run）。

用法：
    .venv/bin/python -m scripts.seed_skill_graph                 # 入库（幂等）
    .venv/bin/python -m scripts.seed_skill_graph --dry-run        # 只预览，不写入
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import get_config
from app.persistence import db as pgdb

RELATIONS_JSON = Path(__file__).resolve().parent.parent / "SkillPilot_skill_relations.json"
ROLES_JSON = Path(__file__).resolve().parent.parent / "SkillPilot_role_competencies.json"
IMPLICIT_DESC = "来自关系图隐式节点"


def _slug(name: str) -> str:
    """技能名 → 小写蛇形 id（与 seed_skills._slug 保持一致）。

    注意：斜杠后不再消费字母 s（旧实现 `(s)?` 会把 'Java/Scala' 误写成
    'java_cala'，现统一为 'java_scala'）。
    """
    s = name.strip().lower()
    s = re.sub(r"[/\\\\()（）]", "_", s)
    s = re.sub(r"[^a-z0-9\u4e00-\u9fff_]+", "_", s)
    return re.sub(r"_+", "_", s).strip("_")


# 隐式节点领域推断：父节点继承不到领域时，按名称/id 关键字兜底归类。
# 值为 relations 中的标准 domain（Lang/Frontend/AI/DB/Data/BigData/Messaging/
# DevOps/OS/Infra/Backend/Architecture/Security/Cloud/Reliability/Quality/CS/Math/Engineering）。
_DOMAIN_HINTS: dict[str, str] = {
    # 语言 / 前端
    "语法": "Language", "标准库": "Language", "协程": "Language",
    "jvm": "Language", "go_并发模型": "Language", "编译": "Language",
    "python": "Language", "go": "Language", "java": "Language",
    "移动端": "Language", "android": "Language", "ios": "Language",
    "vue": "Frontend", "react": "Frontend", "html": "Frontend",
    "css": "Frontend", "ui_ux": "Frontend", "web_基础": "Frontend",
    "web_框架": "Frontend", "api_调用": "Frontend", "前端": "Frontend",
    # AI
    "llm": "AI", "rag": "AI", "embedding": "AI", "向量": "AI",
    "retriever": "AI", "chunk": "AI", "分块": "AI", "重叠": "AI",
    "文本处理": "AI", "checkpoint": "AI", "工具编排": "AI",
    "node_graph": "AI", "node_graph_编排": "AI", "deep_learning": "AI",
    "深度学习": "AI", "transformer": "AI", "模型": "AI", "训练": "AI",
    "数据并行": "AI", "模型并行": "AI", "数据集": "AI", "prompt": "AI",
    "标注": "AI", "语义": "AI", "指标对齐": "AI", "实验": "AI",
    "experimentation": "AI", "试验": "AI", "agent": "AI",
    # DB / 数据
    "sql": "DB", "数据库": "DB", "orm": "DB", "查询": "DB",
    "索引": "DB", "事务": "DB", "主从": "DB", "ddl": "DB",
    "dml": "DB", "扩展": "DB", "持久化": "DB", "文档数据库": "DB",
    "jpa": "DB", "mybatis": "DB", "数据库基础": "DB",
    "数据建模": "Data", "er_建模": "Data", "数仓": "Data", "数据仓库": "Data",
    "数据架构": "Data", "etl": "Data", "抽取": "Data", "清洗": "Data",
    "装载": "Data", "数据管道": "Data", "任务编排": "Data", "依赖回溯": "Data",
    "维度_事实建模": "Data", "bi_工具": "Data", "excel": "Data",
    "可视化": "Data", "业务建模": "Data", "大数据工程": "BigData",
    "hdfs": "BigData", "mapreduce": "BigData", "rdd": "BigData",
    "streaming": "BigData", "spark": "BigData", "hadoop": "BigData",
    "kafka": "Messaging", "topic_分区": "Messaging", "消费者组": "Messaging",
    "exchange": "Messaging", "queue": "Messaging", "消息解耦": "Messaging",
    # DevOps / OS / 网络 / 云
    "docker": "DevOps", "容器": "DevOps", "镜像": "DevOps",
    "k8s": "DevOps", "kubernetes": "DevOps", "pod": "DevOps",
    "ingress": "DevOps", "service": "DevOps", "compose": "DevOps",
    "流水线": "DevOps", "制品": "DevOps", "发布策略": "DevOps",
    "github_actions": "DevOps", "terraform": "DevOps", "iaac": "DevOps",
    "资源编排": "DevOps", "声明式基础": "DevOps", "依赖管理": "DevOps",
    "构建生命周期": "DevOps", "ci_cd": "DevOps",
    "linux": "OS", "shell": "OS", "进程_文件系统": "OS",
    "操作系统基础": "OS", "权限": "OS", "操作系统": "OS",
    "网络": "Infra", "tcp_ip": "Infra", "dns": "Infra",
    "负载均衡": "Infra", "http": "Infra", "状态码": "Infra",
    "请求_响应": "Infra", "rest": "Infra", "rest_api": "Infra",
    "rest_约定": "Infra", "rest_api_对接": "Infra",
    "多云": "Cloud", "iam": "Cloud", "云平台": "Cloud",
    "计算_存储_网络": "Cloud",
    "可观测": "Reliability", "日志": "Reliability", "指标": "Reliability",
    "链路追踪": "Reliability", "监控告警": "Reliability", "sre": "Reliability",
    # 后端 / 架构
    "idl": "Backend", "protocol_buffers": "Backend", "双向流": "Backend",
    "grpc": "Backend", "内嵌容器": "Backend", "自动装配": "Backend",
    "微服务": "Architecture", "服务拆分": "Architecture", "服务发现": "Architecture",
    "熔断": "Architecture", "流量治理": "Architecture", "架构设计": "Architecture",
    "一致性": "Architecture", "容错": "Architecture", "锁_协调": "Architecture",
    "锁": "Architecture",
    # 安全
    "cors": "Security", "xss": "Security", "sqli": "Security",
    "mtls": "Security", "加密": "Security", "密钥": "Security",
    "鉴权": "Security", "漏洞": "Security", "审计": "Security",
    # 质量 / 基础
    "pytest": "Quality", "断言": "Quality", "请求校验": "Quality",
    "缺陷管理": "Quality", "手工测试": "Quality", "自动化测试": "Quality",
    "脚本自动化": "Quality", "测试": "Quality",
    "编程基础": "Computer Science", "计算机基础": "Computer Science",
    "复杂度": "Computer Science", "常用结构": "Computer Science",
    "数据结构": "Computer Science", "算法": "Computer Science",
    "面试基础": "Computer Science",
    "数学基础": "Math", "统计": "Math", "线性代数": "Math", "概率": "Math",
}


def _infer_domain(name: str) -> str | None:
    """按名称关键字推断隐式节点领域；无命中返回 None。"""
    text = _slug(name or "")
    for keyword, domain in _DOMAIN_HINTS.items():
        if keyword in text:
            return domain
    return None


def collect_nodes() -> tuple[dict[str, dict], set[str]]:
    """收集技能节点 {id: {id,name,domain}} 与隐式节点 id 集合。

    显式节点：relations.skills[].skill；隐式节点：仅在 composite_of/requires/related
    中作为引用出现、但不在 relations.skills 列表里的名称（如"编程基础"）。
    """
    nodes: dict[str, dict] = {}
    referenced: set[str] = set()
    rel_data = {}
    if RELATIONS_JSON.exists():
        rel_data = json.loads(RELATIONS_JSON.read_text(encoding="utf-8"))

    for node in rel_data.get("skills", []):
        name = node.get("skill", "").strip()
        if not name:
            continue
        sid = _slug(name)
        nodes[sid] = {"id": sid, "name": name, "domain": node.get("domain"), "implicit": False}
        for field in ("composite_of", "requires", "related"):
            for child in node.get(field, []) or []:
                referenced.add(_slug(str(child).strip()))

    implicit: set[str] = set()
    for rid in referenced - set(nodes):
        # 名称取引用原名（还原）——这里无法还原原文，用 id 作显示名，
        # 稍后在 build 阶段以角色/关系中的原名为准补充到 nodes。
        implicit.add(rid)
    return nodes, implicit


def build(rel_data: dict, roles_data: dict) -> dict:
    """组装三张表的最终内容，供 dry-run / 入库共用。

    返回 {"nodes": [...], "edges": [...], "role_skills": [...]}
    """
    nodes, _implicit_ids = collect_nodes()
    explicit_names = {n["name"]: n for n in nodes.values()}

    def ensure(name: str, domain_hint: str | None = None) -> str:
        """确保技能节点存在（显式或隐式），返回其 id。

        隐式节点优先继承父节点领域（domain_hint），否则按名称关键字推断。
        """
        nname = str(name).strip()
        sid = _slug(nname)
        if sid not in nodes:
            orig = explicit_names.get(nname, {}).get("name", nname)
            nodes[sid] = {
                "id": sid,
                "name": orig,
                "domain": domain_hint or _infer_domain(nname),
                "implicit": True,
            }
            explicit_names.setdefault(nname, nodes[sid])
        return sid

    edges: list[dict] = []
    for node in rel_data.get("skills", []):
        skill = node.get("skill", "").strip()
        if not skill:
            continue
        sid = ensure(skill)
        parent_domain = nodes[sid].get("domain")
        for field, rel in (("requires", "requires"), ("composite_of", "composite_of"), ("related", "related")):
            for child in node.get(field, []) or []:
                cid = ensure(child, domain_hint=parent_domain)
                if rel == "composite_of":
                    # 组合关系：source=父技能, target=子能力
                    edges.append({"source": sid, "target": cid, "rel": rel})
                else:
                    # requires：A 需要 B ⇒ 边 B→A（source=前置, target=技能）
                    # related：source=技能, target=相关技能
                    src, tgt = (cid, sid) if rel == "requires" else (sid, cid)
                    edges.append({"source": src, "target": tgt, "rel": rel})

    role_skills: list[dict] = []
    for role in roles_data.get("roles", []):
        role_id = role.get("role_id", "")
        if not role_id:
            continue
        for req in role.get("required_skills", []):
            name = req.get("skill", "").strip()
            if not name:
                continue
            role_skills.append(
                {
                    "role_id": role_id,
                    "role_name": role.get("role", ""),
                    "category": role.get("category"),
                    "skill_id": ensure(name),
                    "level": req.get("level", 0),
                    "weight": req.get("weight", 1.0),
                    "reason": req.get("reason"),
                }
            )

    # 隐式节点补 description
    for n in nodes.values():
        if n.get("implicit"):
            n["description"] = IMPLICIT_DESC

    return {
        "nodes": sorted(nodes.values(), key=lambda r: r["id"]),
        "edges": sorted(edges, key=lambda r: (r["source"], r["target"], r["rel"])),
        "role_skills": role_skills,
    }


def _migrate_mangled_ids(conn) -> int:
    """修复 _slug 历史 bug 产生的错乱 id（java_cala→java_scala 等），级联更新引用表。

    通过「先插入新行 → 改引用 → 删旧行」避开外键约束（skill_edges/role_skills →
    skill_nodes；user_skills → skills）。幂等：新 id 已存在则跳过。
    """
    rows = conn.execute("SELECT id, name FROM skill_nodes").fetchall()
    renames: list[tuple[str, str]] = []
    for r in rows:
        new_id = _slug(r[1])
        if new_id and new_id != r[0]:
            exists = conn.execute(
                "SELECT 1 FROM skill_nodes WHERE id = %s", (new_id,)
            ).fetchone()
            if not exists:
                renames.append((r[0], new_id))
    if not renames:
        return 0

    for old, new in renames:
        # skill_nodes：先插新行，再改边/岗位引用，最后删旧行
        conn.execute(
            "INSERT INTO skill_nodes (id, name, domain, description) "
            "SELECT %s, name, domain, description FROM skill_nodes WHERE id = %s "
            "ON CONFLICT (id) DO NOTHING",
            (new, old),
        )
        conn.execute("UPDATE skill_edges SET source = %s WHERE source = %s", (new, old))
        conn.execute("UPDATE skill_edges SET target = %s WHERE target = %s", (new, old))
        conn.execute("UPDATE role_skills SET skill_id = %s WHERE skill_id = %s", (new, old))
        conn.execute("DELETE FROM skill_nodes WHERE id = %s", (old,))
        # skills 字典同步迁移
        conn.execute(
            "INSERT INTO skills (id, name, category, description) "
            "SELECT %s, name, category, description FROM skills WHERE id = %s "
            "ON CONFLICT (id) DO NOTHING",
            (new, old),
        )
        conn.execute("UPDATE user_skills SET skill_id = %s WHERE skill_id = %s", (new, old))
        conn.execute("DELETE FROM skills WHERE id = %s", (old,))
    return len(renames)


def _sync_skills_dict(conn, nodes: list[dict]) -> int:
    """统一技能目录：把图谱节点（含隐式）同步进 skills 字典。

    修复"skills 字典（阶段 3 画像抽取用）"与"skill_nodes（阶段 4 图谱/缺口用）"
    两套 ID 割裂：画像抽取与缺口分析从此共用同一技能 ID。
    """
    from app.gap.graph_store import DOMAIN_TO_CATEGORY

    n = 0
    for node in nodes:
        cat = DOMAIN_TO_CATEGORY.get(node.get("domain")) if node.get("domain") else None
        cur = conn.execute(
            """
            INSERT INTO skills (id, name, category, description)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (id) DO UPDATE SET
              name = EXCLUDED.name,
              category = COALESCE(skills.category, EXCLUDED.category),
              description = COALESCE(skills.description, EXCLUDED.description)
            """,
            (node["id"], node["name"], cat, node.get("description")),
        )
        n += cur.rowcount
    return n


def run(dry_run: bool = False) -> int:
    rel_data = json.loads(RELATIONS_JSON.read_text(encoding="utf-8")) if RELATIONS_JSON.exists() else {}
    roles_data = json.loads(ROLES_JSON.read_text(encoding="utf-8")) if ROLES_JSON.exists() else {}
    data = build(rel_data, roles_data)

    if dry_run:
        null_domain = sum(1 for n in data["nodes"] if not n.get("domain"))
        print(
            f"[dry-run] 技能节点 {len(data['nodes'])}，边 {len(data['edges'])}，"
            f"岗位技能 {len(data['role_skills'])} 条（无领域 {null_domain}）"
        )
        for n in data["nodes"]:
            print(f"  [node] {n['id']:<30} {n['name']}  (implicit={n.get('implicit', False)})")
        for e in data["edges"][:20]:
            print(f"  [edge] {e['source']} -{e['rel']}-> {e['target']}")
        return len(data["nodes"])

    cfg = get_config()
    if not cfg.database_url:
        raise SystemExit("DATABASE_URL 未配置")

    n, e, rs = 0, 0, 0
    with pgdb.connect(cfg) as conn:
        # 0) 迁移历史错乱 id（幂等）
        migrated = _migrate_mangled_ids(conn)
        if migrated:
            print(f"已迁移 {migrated} 个错乱技能 id")

        for node in data["nodes"]:
            cur = conn.execute(
                """
                INSERT INTO skill_nodes (id, name, domain, description)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (id) DO UPDATE SET
                  name = EXCLUDED.name,
                  domain = EXCLUDED.domain,
                  description = EXCLUDED.description
                """,
                (
                    node["id"],
                    node["name"],
                    node.get("domain"),
                    node.get("description"),
                ),
            )
            n += cur.rowcount
        for eo in data["edges"]:
            cur = conn.execute(
                """
                INSERT INTO skill_edges (source, target, rel)
                VALUES (%s, %s, %s)
                ON CONFLICT (source, target, rel) DO NOTHING
                """,
                (eo["source"], eo["target"], eo["rel"]),
            )
            e += cur.rowcount
        for r in data["role_skills"]:
            cur = conn.execute(
                """
                INSERT INTO role_skills (role_id, role_name, category, skill_id, level, weight, reason)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (role_id, skill_id) DO UPDATE SET
                  role_name = EXCLUDED.role_name,
                  category = EXCLUDED.category,
                  level = EXCLUDED.level,
                  weight = EXCLUDED.weight,
                  reason = EXCLUDED.reason
                """,
                (r["role_id"], r["role_name"], r["category"], r["skill_id"], r["level"], r["weight"], r["reason"]),
            )
            rs += cur.rowcount
        # 统一技能目录：图谱节点同步进 skills 字典
        synced = _sync_skills_dict(conn, data["nodes"])
    print(
        f"已写入/更新 技能节点 {n}，边 {e}，岗位技能 {rs} 条 "
        f"(节点总数 {len(data['nodes'])}，skills 字典同步 {synced})"
    )
    return len(data["nodes"])


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="生成技能图种子")
    parser.add_argument("--dry-run", action="store_true", help="只预览不写入")
    args = parser.parse_args()
    run(dry_run=args.dry_run)