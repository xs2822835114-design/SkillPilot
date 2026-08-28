"""对话检索辅助：需要时从网络检索参考资料（best-effort，供 LLM 应答）。

能力包括：
- 触发判断：仅对明显的知识性/事实性问题触发，避免对计划类指令无谓检索；
- 查询提炼：去除口语废话、裁剪长度，提升检索命中率；
- 多源降级：DuckDuckGo Lite 为主，失败自动切 Bing；
- 结果清洗：按标题去重，按与查询的相关性打分排序；
- 正文摘要增强：并行抓取前几条网页正文，产出更可靠摘要（短超时，失败保留原 snippet）；
- 输出带编号的 markdown 引用，便于 LLM 在回答中标注来源 [1][2]。
"""
from __future__ import annotations

import logging
import re
import urllib.parse

logger = logging.getLogger(__name__)

# 命中这些词才认为需要联网检索（知识性/事实性问题）
_QUERY_HINTS = (
    "什么是", "是什么", "如何", "怎么", "怎样", "为什么", "区别", "教程",
    "用法", "原理", "最新", "2026", "how", "what", "why", "difference",
    "tutorial", "use", "guide", "compare", "beginner",
)
_MIN_LEN = 6
_TOP = 4
_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "Chrome/124 Safari/537.36"
)


def _requires_search(message: str) -> bool:
    msg = message.strip()
    if len(msg) < _MIN_LEN:
        return False
    low = msg.lower()
    return any(k in low for k in _QUERY_HINTS)


def _clean_query(message: str) -> str:
    """提炼简洁检索词：去掉口语提语、多余空白，并裁剪长度。"""
    q = re.sub(r"\s+", " ", message).strip()
    q = re.sub(
        r"^(请问|帮我|帮我搜一下|麻烦|我想知道|告诉下我|告诉我|你好|你好，|hi|hello)[，,:\s]*",
        "",
        q,
        flags=re.IGNORECASE,
    )
    q = q.strip(" ？?。，,、!！\n")
    return q[:80]


def _http_get(path: str, timeout: float = 7.0):
    import requests

    return requests.get(
        path,
        headers={"User-Agent": _UA, "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8"},
        timeout=timeout,
    )


def _ddg_lite(query: str) -> list[dict]:
    """DuckDuckGo Lite 检索（主源）。"""
    from bs4 import BeautifulSoup

    url = "https://lite.duckduckgo.com/lite/?q=" + urllib.parse.quote(query)
    resp = _http_get(url)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")
    out: list[dict] = []
    for a in soup.select("a[href*='uddg=']"):
        title = a.get_text(strip=True)
        if not title:
            continue
        qs = urllib.parse.parse_qs(urllib.parse.urlparse(a.get("href") or "").query)
        real = qs.get("uddg", [a.get("href")])[0]
        real = str(real)
        if not real.startswith("http"):
            real = f"https:{real}"
        snippet = ""
        table = a.find_parent("table")
        if table is not None:
            sn = table.select_one("td.result-snippet")
            if sn is not None:
                snippet = sn.get_text(" ", strip=True)
        out.append({"title": title, "url": real, "snippet": snippet})
    return out


def _bing(query: str) -> list[dict]:
    """Bing 检索（DDG 失败时的降级源）。"""
    from bs4 import BeautifulSoup

    url = "https://www.bing.com/search?q=" + urllib.parse.quote(query) + "&setlang=zh-hans"
    resp = _http_get(url)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")
    out: list[dict] = []
    for li in soup.select("li.b_algo"):
        a = li.select_one("h2 a")
        if not a or not a.get("href"):
            continue
        p = li.select_one(".b_caption p") or li.select_one("p")
        out.append(
            {
                "title": a.get_text(strip=True),
                "url": a.get("href"),
                "snippet": p.get_text(" ", strip=True) if p else "",
            }
        )
    return out


def _fetch_text(url: str, max_chars: int = 300) -> str:
    """抓取网页正文并截断（短超时；失败抛异常由调用方忽略）。"""
    from bs4 import BeautifulSoup

    resp = requests.get(url, headers={"User-Agent": _UA}, timeout=3)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    text = re.sub(r"\s+", " ", soup.get_text(" ", strip=True))
    # 跳过 "robot/403/you have been blocked" 之类的反爬页
    if not text or "just a moment" in text.lower():
        raise ValueError("blocked or empty")
    return text[:max_chars]


def _dedupe(results: list[dict]) -> list[dict]:
    seen: set[str] = set()
    out: list[dict] = []
    for r in results:
        key = re.sub(r"\W", "", r["title"].lower())
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(r)
    return out


def _score(results: list[dict], query: str) -> list[dict]:
    words = [w for w in re.split(r"\W+", query.lower()) if len(w) > 1]
    for r in results:
        low_title = r["title"].lower()
        low_text = (low_title + " " + (r.get("snippet") or "").lower())
        r["_score"] = sum(
            (2 if w in low_title else 1) for w in words if w in low_text
        )
    return sorted(results, key=lambda r: r.get("_score", 0), reverse=True)


def _enrich(results: list[dict]) -> list[dict]:
    """并行抓取前几条正文，用更长更可靠的摘要替换 snippet；失败保留原值。"""
    try:
        import concurrent.futures
        import requests  # noqa: F401  # 供线程内提前加载避免导入竞态

        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as ex:
            futs = {ex.submit(_fetch_text, r["url"]): r for r in results}
            for fut, r in futs.items():
                try:
                    body = fut.result(timeout=4)
                    if len(body) > len(r.get("snippet") or ""):
                        r["snippet"] = body
                except Exception:  # noqa: BLE001
                    logger.debug("正文抓取失败 %s", r.get("url"), exc_info=True)
    except Exception:  # noqa: BLE001
        logger.debug("正文增强跳过", exc_info=True)
    return results


def search_web(query: str = "", top: int = _TOP) -> str:
    """多源检索并整理为编号 markdown 引用；任意失败返回空串。"""
    if not query:
        return ""
    results: list[dict] = []
    for provider in (_ddg_lite, _bing):
        try:
            results = provider(query)
            if results:
                break
        except Exception:  # noqa: BLE001
            logger.debug("%s 检索失败，尝试下一个源", provider.__name__, exc_info=True)

    results = _dedupe(results)
    if results:
        results = _score(results, query)[:top]
        results = _enrich(results)

    lines: list[str] = []
    for i, r in enumerate(results, 1):
        sn = (r.get("snippet") or "").strip()[:200]
        lines.append(f"[{i}] {r['title']}\n   {sn}\n   {r['url']}")
    return "\n\n".join(lines)


def web_context(message: str) -> str:
    """判断是否需要检索并返回参考上下文（带编号 markdown）；不需要/失败返回空串。"""
    if not _requires_search(message):
        return ""
    return search_web(_clean_query(message))