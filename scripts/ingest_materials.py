"""批量语料入库：读取 materials/manifest.json，逐条经 service.ingest 写入 RAG 知识库。

用途：F10「首批技术资料入库」——把一批 .md/.txt 与 URL 一次性入库。
约定：
- 清单用 JSON，Git 内维护（语料即配置，可追溯、可评审）。
- 文件条目 source 取相对路径，URL 条目 source 取 url；service.ingest 按 source 幂等
  （同 source 重复入库 = 替换式，不产生重复 chunk），故脚本可安全重跑。
- 单条失败不会中断整批，最后给汇总。

运行：
    .venv/bin/python -m scripts.ingest_materials            # 正式入库
    .venv/bin/python -m scripts.ingest_materials --dry-run  # 只打印将入库的条目
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import get_config
from app.rag import service
from app.rag.schemas import RagIngestRequest, RagError

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent.parent
MATERIALS_DIR = ROOT / "materials"
MANIFEST_PATH = MATERIALS_DIR / "manifest.json"


def _yes(s: str) -> str:
    return f"\033[92m{s}\033[0m"


def _no(s: str) -> str:
    return f"\033[91m{s}\033[0m"


def _warn(s: str) -> str:
    return f"\033[93m{s}\033[0m"


def load_manifest() -> list[dict]:
    if not MANIFEST_PATH.exists():
        raise SystemExit(f"语料清单不存在：{MANIFEST_PATH}")
    data = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    items = data.get("items", [])
    if not isinstance(items, list):
        raise SystemExit("manifest.json 的 items 必须是数组")
    return items


def build_request(item: dict) -> RagIngestRequest:
    """把清单条目转为 ingestion 请求：文件读取内容，URL 交给 loader 抓取。"""
    path, url = item.get("path"), item.get("url")
    if bool(path) == bool(url):
        raise ValueError("条目必须且只能提供 path 或 url 之一")
    return RagIngestRequest(
        source_type="text" if path else "url",
        source=item.get("source") or (path or url),
        content=(MATERIALS_DIR / path).read_text(encoding="utf-8") if path else None,
        title=item.get("title"),
        category=item.get("category"),
        lang=item.get("lang"),
        role_target=item.get("role_target"),
        skill_tags=item.get("skill_tags") or [],
    )


def main() -> int:
    ap = argparse.ArgumentParser(description="批量把语料清单中的资料写入 RAG 知识库")
    ap.add_argument("--dry-run", action="store_true", help="只打印将入库的条目，不真正写入")
    args = ap.parse_args()

    cfg = get_config()
    if not cfg.database_url:
        print(_no("DATABASE_URL 未配置，无法入库"))
        return 1

    items = load_manifest()
    print(f"语料清单：{MANIFEST_PATH.name}，共 {len(items)} 条\n")

    if args.dry_run:
        for item in items:
            print(f"  [{item.get('source_type', 'text')}] {item.get('path') or item.get('url')}")
        print(_warn("\n--dry-run：未执行入库。"))
        return 0

    ok = failed = total_chunks = 0
    for i, item in enumerate(items, 1):
        label = item.get("path") or item.get("url") or f"#条 {i}"
        try:
            req = build_request(item)
            resp = service.ingest(cfg, req)
        except RagError as e:
            failed += 1
            print(f"  {_no('[skip]')} {label}  <- {_warn(e.message)}")
            continue
        except ValueError as e:
            failed += 1
            print(f"  {_no('[skip]')} {label}  <- {_warn(str(e))}")
            continue
        except Exception as e:  # noqa: BLE001 - 单条失败不中断整批
            failed += 1
            logger.warning("条目标题入库失败: %s", label, exc_info=True)
            print(f"  {_no('[skip]')} {label}  <- {_warn(str(e))}")
            continue

        ok += 1
        total_chunks += resp.num_chunks
        print(f"  {_yes('[ok]')} {label} -> {resp.doc_id} ({resp.num_chunks} chunks)")

    print(f"\n完成：{_yes(f'{ok} 成功')}，{_no(f'{failed} 失败')}，共 {total_chunks} 个 chunk")
    return 0 if failed == 0 else 2


if __name__ == "__main__":
    logging.basicConfig(level=getattr(logging, get_config().log_level.upper(), logging.INFO))
    raise SystemExit(main())