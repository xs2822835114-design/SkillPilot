"""把 SkillPilot_knowledge_sources.json 的 40 个官方知识源递归抓取并入库。

用法（在项目根目录，.venv 已装依赖）：
    .venv/bin/python -m scripts.ingest_knowledge_sources            # 全量 40 源
    .venv/bin/python -m scripts.ingest_knowledge_sources --dry-run  # 只预览
    .venv/bin/python -m scripts.ingest_knowledge_sources --only KB001,KB002
    .venv/bin/python -m scripts.ingest_knowledge_sources --max-pages 20 --max-depth 2

每个被爬页面以"URL"为幂等键经 service.ingest 入库；失败不中断整批，末尾汇总。
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from concurrent import futures
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import get_config
from app.rag import crawler, service
from app.rag.schemas import RagIngestRequest

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("ingest_knowledge_sources")

_MANIFEST = Path(__file__).resolve().parent.parent / "SkillPilot_knowledge_sources.json"


def load_manifest(path: Path) -> list[dict]:
    data = json.loads(path.read_text(encoding="utf-8"))
    return data.get("sources", [])


def _meta(source: dict, page) -> dict:
    return {
        "source_id": source["id"],
        "source_url": source.get("url"),
        "type": source.get("type"),
        "priority": source.get("priority"),
        "technology": source.get("technology", []),
        "version": source.get("version"),
        "section": page.title or "",
    }


def run(source: dict, cfg, max_depth: int, max_pages: int) -> tuple[str, int, int, int]:
    """抓取并入库单个知识源，返回 (source_id, pages, ingested, failed_pages)。"""
    res = crawler.crawl_source(
        source["url"], max_depth=max_depth, max_pages=max_pages
    )
    ok = 0
    page_failed = 0
    for page in res.pages:
        try:
            req = RagIngestRequest(
                source_type="url",
                source=page.url,
                title=page.title or source.get("title"),
                content=None,
                category=source.get("category"),
                role_target=source.get("role_target"),
                skill_tags=source.get("technology", []),
                meta=_meta(source, page),
            )
            service.ingest(cfg, req)
            ok += 1
        except Exception as exc:  # noqa: BLE001
            page_failed += 1
            logger.warning("[%s] 入库失败 %s: %s", source["id"], page.url, exc)
    logger.info(
        "[%s] %s：pages=%d ingested=%d (fetched=%d failed=%d skipped=%d)",
        source["id"],
        source.get("title"),
        len(res.pages),
        ok,
        res.fetched,
        res.failed,
        res.skipped,
    )
    return source["id"], len(res.pages), ok, page_failed


@dataclass
class _Stats:
    pages: int = 0
    ingested: int = 0
    page_failed: int = 0
    source_failed: int = 0


def main() -> int:
    ap = argparse.ArgumentParser(description="SkillPilot 首批知识源抓取入库")
    ap.add_argument("--manifest", default=str(_MANIFEST))
    ap.add_argument("--only", help="逗号分隔的 source id，仅处理这些")
    ap.add_argument("--max-depth", type=int, default=2)
    ap.add_argument("--max-pages", type=int, default=40)
    ap.add_argument("--workers", type=int, default=4, help="并发抓取的知识源数量")
    ap.add_argument("--dry-run", action="store_true", help="只打印将要处理的知识源")
    args = ap.parse_args()

    sources = load_manifest(Path(args.manifest))
    if args.only:
        ids = {x.strip() for x in args.only.split(",") if x.strip()}
        sources = [s for s in sources if s["id"] in ids]
    if not sources:
        logger.error("没有待处理的知识源")
        return 2

    for s in sources:
        print(f"[dry] {s['id']:6s} {s.get('title',''):40s} {s['url']}")
    if args.dry_run:
        return 0

    stats = _Stats()
    with futures.ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
        results = pool.map(
            lambda s: run(s, get_config(), args.max_depth, args.max_pages), sources
        )
        for sid, pages, ingested, page_failed in results:
            stats.pages += pages
            stats.ingested += ingested
            stats.page_failed += page_failed
            print(f"✔ {sid}: 入库 {ingested}/{pages} 页")

    print(
        "\n完成：知识源=%d 页面=%d 成功入库=%d 页级失败=%d"
        % (len(sources), stats.pages, stats.ingested, stats.page_failed)
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())