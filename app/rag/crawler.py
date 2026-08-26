"""网页爬虫：从知识源入口 URL 递归抓取同域子页（限深度/限页数/礼貌限速）。

对每个页面用 loader.crawler_extract 做正文清洗 + 标题提取，
返回页面列表供 ingest 脚本逐页以"URL 幂等"入库。
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from urllib.parse import urljoin, urlparse

import lxml.html
import requests

from app.rag import loader

logger = logging.getLogger(__name__)

# 静态资源 / 明显非文档页面，跳过
_SKIP_SUFFIX = (
    ".pdf", ".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp",
    ".zip", ".tar", ".gz", ".gz2", ".xz",
    ".woff", ".woff2", ".ttf", ".eot", ".css", ".js",
    ".mp4", ".mp3", ".doc", ".docx", ".xls", ".xlsx", ".csv",
)
_SKIP_PREFIX = ("mailto:", "javascript:", "tel:")


@dataclass
class Page:
    url: str
    title: str | None
    text: str


@dataclass
class CrawlResult:
    pages: list[Page] = field(default_factory=list)
    fetched: int = 0
    failed: int = 0
    skipped: int = 0


def _same_netloc(a: str, b: str) -> bool:
    return urlparse(a).netloc == urlparse(b).netloc


def _is_doc_link(href: str, base: str) -> bool:
    if not href:
        return False
    if href.startswith(_SKIP_PREFIX):
        return False
    for s in _SKIP_SUFFIX:
        if href.lower().endswith(s):
            return False
    if href.startswith("#"):
        return False
    parsed = urlparse(href)
    if parsed.scheme and parsed.scheme not in ("http", "https"):
        return False
    return True


def crawl_source(
    start_url: str,
    max_depth: int = 2,
    max_pages: int = 40,
    delay: float = 0.4,
    timeout: int = 20,
    headers: dict | None = None,
) -> CrawlResult:
    """从 start_url 做同域限宽优先爬取。"""
    if not (start_url.startswith("http://") or start_url.startswith("https://")):
        raise ValueError(f"start_url 必须为 http(s)://，got {start_url}")

    default_headers = {
        "User-Agent": "Mozilla/5.0 (compatible; SkillMap-RAG/0.1; +knowledge-crawler)",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en,zh;q=0.9",
    }
    headers = {**default_headers, **(headers or {})}

    result = CrawlResult()
    visited: set[str] = set()
    queue: list[tuple[str, int]] = [(start_url, 0)]  # (url, depth)

    while queue and len(visited) < max_pages:
        url, depth = queue.pop(0)
        if url in visited:
            continue
        # 清掉 fragment，保证 URL 幂等
        norm = urljoin(url, urlparse(url)._replace(fragment="").geturl())
        if not _same_netloc(norm, start_url) or norm in visited:
            continue
        visited.add(norm)

        try:
            resp = requests.get(norm, timeout=timeout, headers=headers)
            resp.raise_for_status()
        except requests.RequestException as exc:
            result.failed += 1
            logger.warning("抓取失败 %s: %s", norm, exc)
            time.sleep(delay)
            continue

        text, title = loader.crawler_extract(resp.text, norm)
        if not text:
            result.skipped += 1
        else:
            result.pages.append(Page(url=norm, title=title, text=text))
        result.fetched += 1

        # 收集子链接（同域、文档类）
        if max_pages and len(visited) + 1 < max_pages and depth < max_depth:
            try:
                tree = lxml.html.fromstring(resp.text)
                tree.make_links_absolute(norm)
                for a in tree.xpath("//a[@href]"):
                    href = a.get("href", "")
                    if not _is_doc_link(href, norm):
                        continue
                    child = urljoin(norm, href)
                    child = urlparse(child)._replace(fragment="").geturl()
                    if _same_netloc(child, start_url) and child not in visited:
                        queue.append((child, depth + 1))
            except (ValueError, OSError, lxml.etree.ParserError) as exc:  # type: ignore[attr-defined]
                logger.debug("链接解析失败 %s: %s", norm, exc)

        time.sleep(delay)

    logger.info(
        "爬取完成 %s：pages=%d fetched=%d failed=%d skipped=%d",
        start_url,
        len(result.pages),
        result.fetched,
        result.failed,
        result.skipped,
    )
    return result