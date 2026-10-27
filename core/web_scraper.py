"""Tier-2 deep full-text web ingestion: trafilatura main-content extraction with BeautifulSoup & Wayback Machine fallbacks."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Optional, Tuple
from urllib.parse import urlparse

import urllib3

MAX_ARTICLE_WORDS = 3500
MAX_ARTICLE_CHARS = 30000  # defensive ceiling for scripts without whitespace word boundaries (CJK)
MIN_ARTICLE_WORDS = 100  # extractions under 100 words trigger fallback or are treated as failed
MIN_ARTICLE_CHARS = 250
MAX_DOWNLOAD_BYTES = 4_000_000

_BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9,ko;q=0.8",
    "Sec-Ch-Ua": '"Chromium";v="124", "Google Chrome";v="124", "Not-A.Brand";v="99"',
    "Sec-Ch-Ua-Mobile": "?0",
    "Sec-Ch-Ua-Platform": '"Windows"',
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
}

_BOILERPLATE_TAGS = (
    "script", "style", "noscript", "nav", "header", "footer", "aside", "form",
    "iframe", "svg", "button", "figure", "menu", "dialog",
)


@dataclass
class WebArticle:
    """A cleaned full-text article."""

    url: str
    title: str
    text: str

    @property
    def word_count(self) -> int:
        return len(self.text.split())


def cap_article_text(text: str, max_words: int = MAX_ARTICLE_WORDS, max_chars: int = MAX_ARTICLE_CHARS) -> str:
    """Trim text to at most `max_words` whitespace words (and `max_chars`), keeping paragraph breaks intact."""
    kept: list[str] = []
    words_left = max_words
    chars_left = max_chars
    for paragraph in re.split(r"\n{2,}", text.strip()):
        paragraph = paragraph.strip()
        if not paragraph:
            continue
        paragraph_words = paragraph.split()
        if len(paragraph_words) > words_left:
            paragraph = " ".join(paragraph_words[:words_left])
            words_left = 0
        else:
            words_left -= len(paragraph_words)
        if len(paragraph) > chars_left:
            paragraph = paragraph[:chars_left].rstrip()
            chars_left = 0
        else:
            chars_left -= len(paragraph)
        if paragraph:
            kept.append(paragraph)
        if words_left <= 0 or chars_left <= 0:
            break
    return "\n\n".join(kept).strip()


def _download(url: str, timeout: int) -> Tuple[Optional[bytes], str, int]:
    """Download `url` following redirects; returns (body, final_url, status_code). Body is None on any failure."""
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return None, url, 0
    pool = urllib3.PoolManager(
        timeout=urllib3.Timeout(connect=timeout, read=timeout),
        retries=urllib3.Retry(total=2, redirect=5, backoff_factor=0.3),
        headers=_BROWSER_HEADERS,
    )
    try:
        response = pool.request("GET", url, preload_content=False)
        try:
            status = response.status
            if status >= 400:
                return None, url, status
            content_type = (response.headers.get("Content-Type") or "").lower()
            if content_type and not any(k in content_type for k in ("html", "xml", "text")):
                return None, url, status
            body = response.read(MAX_DOWNLOAD_BYTES, decode_content=True)
            final_url = getattr(response, "url", None) or url
            return body, str(final_url), status
        finally:
            response.release_conn()
    except Exception:
        return None, url, 0
    finally:
        pool.clear()


def _extract_with_trafilatura(body: bytes, url: str) -> Tuple[str, str]:
    try:
        import trafilatura
    except Exception:
        return "", ""
    try:
        text = trafilatura.extract(
            body,
            url=url,
            include_comments=False,
            include_tables=True,
            include_links=False,
            favor_precision=True,
            deduplicate=True,
        ) or ""
    except Exception:
        text = ""
    title = ""
    try:
        meta = trafilatura.extract_metadata(body, default_url=url)
        title = (getattr(meta, "title", "") or "").strip() if meta else ""
    except Exception:
        title = ""
    return text, title


def _extract_with_beautifulsoup(body: bytes) -> Tuple[str, str]:
    try:
        from bs4 import BeautifulSoup
    except Exception:
        return "", ""
    try:
        soup = BeautifulSoup(body, "html.parser")
    except Exception:
        return "", ""
    title = (soup.title.string or "").strip() if soup.title and soup.title.string else ""
    for tag_name in _BOILERPLATE_TAGS:
        for tag in soup.find_all(tag_name):
            tag.decompose()
    for tag in soup.find_all(attrs={"class": re.compile(r"(?:^|\s)(ad|ads|advert|banner|cookie|promo|sidebar|share|social|newsletter|subscribe|related|comments?)(?:\s|$)", re.I)}):
        tag.decompose()

    # Prioritize <article>, <main>, or .content containers
    container = (
        soup.find("article")
        or soup.find("main")
        or soup.find(attrs={"class": re.compile(r"(?:^|\s)(content|article-body|post-content|main-content)(?:\s|$)", re.I)})
        or soup.body
        or soup
    )
    paragraphs = [p.get_text(" ", strip=True) for p in container.find_all(["p", "h1", "h2", "h3", "li"])]
    paragraphs = [p for p in paragraphs if len(p.split()) >= 4 or len(p) >= 30]
    return "\n\n".join(paragraphs), title


def _fetch_wayback_snapshot_url(url: str, timeout: int = 4) -> Optional[str]:
    """Query Wayback Machine API to retrieve the latest cached snapshot URL for blocked/failed pages."""
    api_url = f"https://archive.org/wayback/available?url={url}"
    pool = urllib3.PoolManager(timeout=urllib3.Timeout(connect=timeout, read=timeout))
    try:
        resp = pool.request("GET", api_url, headers=_BROWSER_HEADERS)
        if resp.status == 200:
            data = json.loads(resp.data.decode("utf-8", errors="replace"))
            closest = data.get("archived_snapshots", {}).get("closest", {})
            if closest.get("available") and closest.get("url"):
                return str(closest["url"])
    except Exception:
        pass
    finally:
        pool.clear()
    return None


def extract_clean_web_article(url: str, timeout: int = 7) -> str | None:
    """
    Extract clean article body text from `url` using trafilatura, falling back to BeautifulSoup
    main article parsing (<article>, <main>, .content) and the Wayback Machine on 403/404/429 blocks.
    Enforces an upper bound of 3,500 words per article.
    """
    body, final_url, status = _download(url, timeout)

    # If blocked (403/404/429/empty), attempt Wayback Machine archive fallback
    if not body or status in {403, 404, 429}:
        snapshot_url = _fetch_wayback_snapshot_url(url, timeout=min(timeout, 5))
        if snapshot_url:
            body, final_url, _ = _download(snapshot_url, timeout)

    if not body:
        return None

    # Step 1: Trafilatura extraction
    text, _ = _extract_with_trafilatura(body, final_url)
    word_count = len(text.split())

    # Step 2: BeautifulSoup fallback if trafilatura yields < 100 words or fails
    if word_count < MIN_ARTICLE_WORDS:
        fallback_text, _ = _extract_with_beautifulsoup(body)
        if len(fallback_text.split()) > word_count:
            text = fallback_text
            word_count = len(text.split())

    # Step 3: If still under 100 words and not yet tried Wayback, try snapshot
    if word_count < MIN_ARTICLE_WORDS and "web.archive.org" not in final_url:
        snapshot_url = _fetch_wayback_snapshot_url(url, timeout=min(timeout, 5))
        if snapshot_url:
            s_body, s_final_url, _ = _download(snapshot_url, timeout)
            if s_body:
                s_text, _ = _extract_with_trafilatura(s_body, s_final_url)
                if len(s_text.split()) >= MIN_ARTICLE_WORDS:
                    text = s_text

    text = cap_article_text(text, max_words=MAX_ARTICLE_WORDS)
    if len(text.split()) < 15 and len(text) < MIN_ARTICLE_CHARS:
        return None
    return text


def fetch_web_article(url: str, timeout: int = 7) -> Optional[WebArticle]:
    """Fetch and clean an article. Returns WebArticle or None for paywalls/timeouts/boilerplate."""
    body, final_url, status = _download(url, timeout)
    if not body or status in {403, 404, 429}:
        snapshot_url = _fetch_wayback_snapshot_url(url, timeout=min(timeout, 5))
        if snapshot_url:
            body, final_url, _ = _download(snapshot_url, timeout)

    if not body:
        return None

    text, title = _extract_with_trafilatura(body, final_url)
    if len(text.split()) < MIN_ARTICLE_WORDS:
        fallback_text, fallback_title = _extract_with_beautifulsoup(body)
        if len(fallback_text.split()) > len(text.split()):
            text = fallback_text
        title = title or fallback_title

    text = cap_article_text(text, max_words=MAX_ARTICLE_WORDS)
    if len(text.split()) < 15 and len(text) < MIN_ARTICLE_CHARS:
        return None

    resolved_title = title.strip() or urlparse(final_url).netloc
    return WebArticle(url=final_url, title=resolved_title, text=text)
