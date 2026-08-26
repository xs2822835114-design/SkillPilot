"""Loader：把 url / text 解析为纯文本 + 来源元数据。

阶段 2 支持 text 与 url（网页用 trafilatura 抽取正文与标题，去除导航/页脚）；
file 留接口（可后续接 PDF 等）。
"""
from __future__ import annotations

import logging

import requests
import trafilatura
from trafilatura.settings import use_config

from app.rag.schemas import RagIngestRequest

logger = logging.getLogger(__name__)


class LoadResult:
    def __init__(self, text: str, source: str, source_type: str, title: str | None = None) -> None:
        self.text = text
        self.source = source
        self.source_type = source_type
        self.title = title


def load(req: RagIngestRequest) -> LoadResult:
    if req.source_type == "text":
        if not req.content:
            raise ValueError("source_type=text 时必须提供 content")
        return LoadResult(req.content, req.source or "text://inline", "text")

    if req.source_type == "url":
        return _fetch_url(req.source)

    raise ValueError(f"暂不支持 source_type={req.source_type}")


def _trafconfig() -> use_config:
    """关闭外部引用、语言识别等遥测/联网，只做正文抽取。"""
    cfg = use_config()
    cfg.set("DEFAULT", "EXTRACTION_TIMEOUT", "0")
    return cfg


def _fetch_url(url: str | None) -> LoadResult:
    if not url:
        raise ValueError("source_type=url 时必须提供 source")
    if not (url.startswith("http://") or url.startswith("https://")):
        raise ValueError("url 必须以 http(s):// 开头")

    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; SkillMap-RAG/0.1; +knowledge-crawler)",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en,zh;q=0.9",
    }
    resp = requests.get(url, timeout=30, headers=headers)
    resp.raise_for_status()
    if "text/html" not in (resp.headers.get("content-type", "") or "") and not resp.text.lstrip().startswith("<"):
        # 非 HTML（如纯文本/JSON），原样当正文
        return LoadResult(resp.text, url, "url", title=None)

    html = resp.text
    extracted = trafilatura.extract(
        html,
        config=_trafconfig(),
        include_comments=False,
        include_tables=True,
        favor_precision=False,
        output_format="markdown",
    )
    text = (extracted or "").strip()
    if not text:
        logger.warning("正文抽取为空：%s", url)
        return LoadResult(text, url, "url", title=None)

    # trafilatura 开头常为 <h1> 标题，取其作为页标题
    first = None
    for line in text.splitlines()[:5]:
        line = line.strip()
        if line.startswith("#"):
            first = line.lstrip("#").strip()
            break
    return LoadResult(text, url, "url", title=first or None)


def crawler_extract(html: str, url: str) -> tuple[str, str | None]:
    """供 crawler 复用：输入 HTML，返回 (清洗后 markdown 正文, 一级标题)。"""
    try:
        text = trafilatura.extract(
            html,
            config=_trafconfig(),
            include_comments=False,
            include_tables=True,
            output_format="markdown",
        )
    except Exception:  # noqa: BLE001
        logger.warning("trafilatura 抽取异常：%s", url, exc_info=True)
        return "", None
    text = (text or "").strip()
    title = None
    for line in text.splitlines()[:5]:
        s = line.strip()
        if s.startswith("#"):
            title = s.lstrip("#").strip()
            break
    return text, title