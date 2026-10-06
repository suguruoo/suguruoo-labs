# data/crawler.py
"""DynamoDB ドキュメントクローラー。

requests + BeautifulSoup4 で HTML を取得しテキストを抽出する。
PDF はダウンロードして pypdf で抽出する。
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from data.sources import ALL_SOURCES, SourceEntry

logger = logging.getLogger(__name__)

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (compatible; DynamoDB-RAG-Crawler/1.0; "
        "+https://github.com/suguruoo/suguruoo-labs)"
    )
}
_REQUEST_DELAY = 1.5  # seconds between requests
_MAX_PAGES_PER_SOURCE = 80


@dataclass
class CrawledPage:
    """クロール結果の1ページ分。"""

    url: str
    lang: str
    source_type: str
    title: str
    section: str
    content: str
    keywords: list[str] = field(default_factory=list)


def _extract_keywords(soup: BeautifulSoup) -> list[str]:
    """meta keywords / h2 見出し からキーワードを抽出する。"""
    keywords: list[str] = []
    meta_kw = soup.find("meta", attrs={"name": "keywords"})
    if meta_kw and meta_kw.get("content"):
        keywords.extend([k.strip() for k in meta_kw["content"].split(",")])
    for h2 in soup.find_all("h2")[:5]:
        text = h2.get_text(strip=True)
        if text:
            keywords.append(text)
    return list(dict.fromkeys(keywords))  # dedupe


def _extract_section(soup: BeautifulSoup) -> str:
    """breadcrumb / h1 からセクション名を取得する。"""
    breadcrumb = soup.find("div", class_=lambda c: c and "breadcrumb" in c.lower())
    if breadcrumb:
        items = [a.get_text(strip=True) for a in breadcrumb.find_all("a")]
        if items:
            return " > ".join(items[-2:])
    h1 = soup.find("h1")
    return h1.get_text(strip=True) if h1 else ""


def _clean_text(soup: BeautifulSoup) -> str:
    """不要タグを除去して本文テキストを返す。"""
    for tag in soup.find_all(["script", "style", "nav", "footer", "header"]):
        tag.decompose()
    main = (
        soup.find("main")
        or soup.find("div", id="main-content")
        or soup.find("div", class_=lambda c: c and "content" in c.lower())
        or soup.body
    )
    if main is None:
        return ""
    text = main.get_text(separator="\n", strip=True)
    lines = [line for line in text.splitlines() if len(line.strip()) > 10]
    return "\n".join(lines)


def _get_child_links(soup: BeautifulSoup, base_url: str, base_domain: str) -> list[str]:
    """同一ドメイン内のリンクを収集する。"""
    links: list[str] = []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        full_url = urljoin(base_url, href)
        parsed = urlparse(full_url)
        if parsed.netloc == base_domain and parsed.scheme in ("http", "https"):
            clean = full_url.split("#")[0].rstrip("/")
            if clean not in links:
                links.append(clean)
    return links


def crawl_source(entry: SourceEntry, max_pages: int = _MAX_PAGES_PER_SOURCE) -> list[CrawledPage]:
    """1つのソースエントリをクロールして CrawledPage リストを返す。

    Args:
        entry: 収集対象URLエントリ。
        max_pages: 最大ページ数（超過したら打ち切り）。

    Returns:
        クロール結果のページリスト。
    """
    base_domain = urlparse(entry.url).netloc
    visited: set[str] = set()
    queue: list[str] = [entry.url]
    pages: list[CrawledPage] = []

    while queue and len(pages) < max_pages:
        url = queue.pop(0)
        url_clean = url.split("#")[0].rstrip("/")
        if url_clean in visited:
            continue
        visited.add(url_clean)

        try:
            resp = requests.get(url, headers=_HEADERS, timeout=15)
            resp.raise_for_status()
        except requests.RequestException as exc:
            logger.warning("fetch failed: %s – %s", url, exc)
            time.sleep(_REQUEST_DELAY)
            continue

        content_type = resp.headers.get("Content-Type", "")
        if "html" not in content_type:
            logger.debug("skip non-html: %s (%s)", url, content_type)
            time.sleep(_REQUEST_DELAY)
            continue

        soup = BeautifulSoup(resp.text, "lxml")

        # meta refresh リダイレクトを検出してフォロー（AWS docs 対応）
        meta_refresh = soup.find("meta", attrs={"http-equiv": lambda v: v and v.lower() == "refresh"})
        if meta_refresh:
            content_val = meta_refresh.get("content", "")
            # "0;URL=Introduction.html" 形式をパース
            if "url=" in content_val.lower():
                redirect_url = content_val.lower().split("url=", 1)[1].strip().strip("'\"")
                redirect_full = urljoin(url, redirect_url)
                redirect_clean = redirect_full.split("#")[0].rstrip("/")
                if redirect_clean not in visited:
                    queue.insert(0, redirect_clean)
                logger.debug("meta refresh → %s", redirect_clean)
            time.sleep(_REQUEST_DELAY)
            continue
        title_tag = soup.find("title")
        title = title_tag.get_text(strip=True) if title_tag else url

        content = _clean_text(soup)
        if len(content) < 50:
            logger.debug("skip short content: %s", url)
            time.sleep(_REQUEST_DELAY)
            continue

        page = CrawledPage(
            url=url_clean,
            lang=entry.lang,
            source_type=entry.source_type,
            title=title,
            section=_extract_section(soup),
            content=content,
            keywords=_extract_keywords(soup),
        )
        pages.append(page)
        logger.info("crawled [%d/%d] %s", len(pages), max_pages, url_clean)

        child_links = _get_child_links(soup, url, base_domain)
        for link in child_links:
            if link not in visited:
                queue.append(link)

        time.sleep(_REQUEST_DELAY)

    logger.info("crawl_source done: %s → %d pages", entry.label, len(pages))
    return pages


def crawl_all(max_pages_per_source: int = _MAX_PAGES_PER_SOURCE) -> list[CrawledPage]:
    """全ソースをクロールして結果をまとめて返す。

    sources.py が個別ページ URL を直接列挙しているため、
    各エントリを max_pages=1 で処理する（子リンクは辿らない）。
    blog/faq など index ページは max_pages_per_source で子リンクを辿る。

    Args:
        max_pages_per_source: blog/faq エントリごとの最大ページ数。

    Returns:
        全ページのリスト。
    """
    all_pages: list[CrawledPage] = []
    for entry in ALL_SOURCES:
        logger.info("=== crawling: %s ===", entry.label)
        # developer_guide / data_modeling は個別ページ直指定なので max=1
        if entry.source_type in ("developer_guide", "data_modeling"):
            pages = crawl_source(entry, max_pages=1)
        else:
            pages = crawl_source(entry, max_pages=max_pages_per_source)
        all_pages.extend(pages)
    logger.info("crawl_all done: total %d pages", len(all_pages))
    return all_pages
