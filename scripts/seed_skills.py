"""生成技能字典种子（阶段 3）：由阶段 2 的两份 JSON 技能名归一去重后写入 skills 表。

用法：
    .venv/bin/python -m scripts.seed_skills                 # 入库（幂等）
    .venv/bin/python -m scripts.seed_skills --dry-run        # 只预览，不写入
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

# 阶段 2 提供的两份知识库 JSON（技能名来源）
RELATIONS_JSON = Path(__file__).resolve().parent.parent / "SkillPilot_skill_relations.json"
ROLES_JSON = Path(__file__).resolve().parent.parent / "SkillPilot_role_competencies.json"


def _slug(name: str) -> str:
    """技能名 → 小写蛇形 id；中文保留，斜杠/括号转下划线或去除。"""
    s = name.strip().lower()
    s = re.sub(r"[/\\\\()（）](s)?", "_", s)
    s = re.sub(r"[^a-z0-9\u4e00-\u9fff_]+", "_", s)
    return re.sub(r"_+", "_", s).strip("_")


def collect_skills() -> list[dict]:
    """从两份 JSON 收集 {id, name, category}，按 id 去重。"""
    merged: dict[str, dict] = {}
    if RELATIONS_JSON.exists():
        data = json.loads(RELATIONS_JSON.read_text(encoding="utf-8"))
        for node in data.get("skills", []):
            name = node.get("skill", "").strip()
            if not name:
                continue
            merged.setdefault(
                _slug(name),
                {"id": _slug(name), "name": name, "category": node.get("domain")},
            )
    if ROLES_JSON.exists():
        data = json.loads(ROLES_JSON.read_text(encoding="utf-8"))
        for role in data.get("roles", []):
            for req in role.get("required_skills", []):
                name = req.get("skill", "").strip()
                if not name:
                    continue
                merged.setdefault(
                    _slug(name),
                    {"id": _slug(name), "name": name, "category": role.get("category")},
                )
    return sorted(merged.values(), key=lambda r: r["id"])


def run(dry_run: bool = False) -> int:
    skills = collect_skills()
    print(f"技能字典共 {len(skills)} 条")

    cfg = get_config()
    if not cfg.database_url:
        raise SystemExit("DATABASE_URL 未配置")

    inserted = 0
    with pgdb.connect(cfg) as conn:
        for s in skills:
            if dry_run:
                print(f"  [dry-run] {s['id']:<28} {s['name']}  ({s['category']})")
                continue
            cur = conn.execute(
                """
                INSERT INTO skills (id, name, category, description)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (id) DO UPDATE SET
                  name = EXCLUDED.name,
                  category = EXCLUDED.category
                """,
                (s["id"], s["name"], s["category"], None),
            )
            inserted += cur.rowcount
    if not dry_run:
        print(f"已写入/更新 {inserted} 条技能字典")
    return len(skills)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="生成技能字典种子")
    parser.add_argument("--dry-run", action="store_true", help="只预览不写入")
    args = parser.parse_args()
    run(dry_run=args.dry_run)