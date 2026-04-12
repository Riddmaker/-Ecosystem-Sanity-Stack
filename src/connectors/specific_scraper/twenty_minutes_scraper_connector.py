"""
20 Minuten Switzerland — Scraper connector.

Extracts articles directly from www.20min.ch.

Strategy:
  - Index pages: extract /story/ links via href pattern — no CSS class dependency
  - Content:     articleBody field from JSON-LD NewsArticle schema (stable, publisher-provided)
  - Metadata:    headline, description, datePublished, author from same JSON-LD block
  - Category:    BreadcrumbList JSON-LD block, parsed in the same pass
  - Fallback:    trafilatura if articleBody is missing

Dependencies:
    pip install requests beautifulsoup4 trafilatura
"""

import json
import re
import time
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from src.connectors.abstract.models import Article
from src.connectors.abstract.scraper_connector import BaseScraperConnector


BASE_URL = "https://www.20min.ch"

DEFAULT_SECTIONS = [
    "/",
    "/news",
    "/sport",
    "/wirtschaft",
    "/leben",
    "/digital",
]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "de-CH,de;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

CRAWL_DELAY = 1.0


class TwentyMinutesScraperConnector(BaseScraperConnector):
    """
    Scrapes articles from www.20min.ch.

    Usage:
        connector = TwentyMinutesScraperConnector()
        articles = connector.get_articles()

        connector = TwentyMinutesScraperConnector(sections=["/news", "/wirtschaft"])
        articles = connector.get_articles(max_articles=10)
    """

    SOURCE = "20min.ch"
    LANGUAGE = "de"

    def __init__(self, sections: Optional[list[str]] = None, crawl_delay: float = CRAWL_DELAY):
        self._sections = sections or DEFAULT_SECTIONS
        self._crawl_delay = crawl_delay
        self._session = requests.Session()
        self._session.headers.update(HEADERS)

    @property
    def index_urls(self) -> list[str]:
        return [urljoin(BASE_URL, section) for section in self._sections]

    def fetch_html(self, url: str, headers: Optional[dict] = None) -> str:
        """Use the configured session (with browser headers) instead of plain requests.get."""
        response = self._session.get(url, headers=headers or {}, timeout=15)
        response.raise_for_status()
        return response.text

    # ------------------------------------------------------------------
    # Index page
    # ------------------------------------------------------------------

    def extract_article_links(self, html: str, index_url: str) -> list[str]:
        """Extract unique /story/ URLs from a listing page."""
        soup = BeautifulSoup(html, "html.parser")
        seen = set()
        links = []
        for tag in soup.find_all("a", href=re.compile(r"^/story/")):
            href = tag["href"].split("?")[0]
            full_url = urljoin(BASE_URL, href)
            if full_url not in seen:
                seen.add(full_url)
                links.append(full_url)
        return links

    # ------------------------------------------------------------------
    # Article page
    # ------------------------------------------------------------------

    def parse_article(self, html: str, url: str) -> Article:
        news_article, breadcrumb = self._parse_json_ld(html)

        content = self._strip_html(news_article.get("articleBody", ""))
        if not content:
            content = self._trafilatura_fallback(html, url)

        category, tags = self._parse_breadcrumb(breadcrumb)

        return Article(
            title=news_article.get("headline", ""),
            url=url,
            source_article_id=self._extract_article_id(url),
            content=content,
            summary=news_article.get("description"),
            published_at=self._parse_datetime(news_article.get("datePublished")),
            source=self.SOURCE,
            language=self.LANGUAGE,
            author=self._parse_author(news_article.get("author")),
            category=category,
            tags=tags,
            word_count=len(content.split()) if content else None,
            article_type=self._detect_article_type(news_article),
            connector_type="scraper",
            raw=news_article,
        )

    def _parse_json_ld(self, html: str) -> tuple[dict, list]:
        """
        Parse all JSON-LD blocks in one pass.
        Returns (NewsArticle dict, BreadcrumbList itemListElement).
        """
        soup = BeautifulSoup(html, "html.parser")
        news_article = {}
        breadcrumb_items = []

        for script in soup.find_all("script", type="application/ld+json"):
            try:
                data = json.loads(script.string or "")
            except (json.JSONDecodeError, AttributeError):
                continue

            # Normalize to a flat list of blocks — handles three shapes:
            # 1. { "@type": "NewsArticle", ... }          → direct object
            # 2. [ { "@type": "..." }, ... ]              → top-level list
            # 3. { "@graph": [ { "@type": "..." }, ... ] } → @graph wrapper
            if isinstance(data, list):
                blocks = data
            elif "@graph" in data:
                blocks = data["@graph"]
            else:
                blocks = [data]

            for block in blocks:
                t = block.get("@type")
                if t == "NewsArticle" and not news_article:
                    news_article = block
                elif t == "BreadcrumbList" and not breadcrumb_items:
                    breadcrumb_items = block.get("itemListElement", [])

            if news_article and breadcrumb_items:
                break  # got everything we need

        return news_article, breadcrumb_items

    @staticmethod
    def _parse_breadcrumb(items: list) -> tuple[Optional[str], list[str]]:
        """
        Extract category and tags from BreadcrumbList items.
        Structure: News > Category > Subcategory > Article title (last item skipped)
        """
        crumbs = []
        for item in items[:-1]:  # skip last (= article title)
            name = item.get("item", {}).get("name") or item.get("name", "")
            if name and name.lower() != "news":
                crumbs.append(name)
        return (crumbs[0] if crumbs else None), crumbs[1:]

    @staticmethod
    def _parse_author(author: Optional[dict | list | str]) -> Optional[str]:
        if not author:
            return None
        if isinstance(author, dict):
            return author.get("name")
        if isinstance(author, list) and author:
            first = author[0]
            return first.get("name") if isinstance(first, dict) else str(first)
        return str(author)

    @staticmethod
    def _parse_datetime(value: Optional[str]) -> datetime:
        if not value:
            return datetime.now(tz=timezone.utc)
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            return datetime.now(tz=timezone.utc)

    @staticmethod
    def _extract_article_id(url: str) -> str | None:
        """Extract the numeric article ID from the end of a 20min /story/ URL."""
        match = re.search(r"-(\d{6,12})$", url.rstrip("/").split("?")[0])
        return match.group(1) if match else None

    @staticmethod
    def _detect_article_type(news_article: dict) -> str:
        """Guess article type from JSON-LD fields."""
        # Liveblogs have a very old datePublished but recent dateModified
        if news_article.get("liveBlogUpdate") or news_article.get("@type") == "LiveBlogPosting":
            return "liveblog"
        # Heuristic: if alternativeHeadline looks like a live-ticker label
        alt = (news_article.get("alternativeHeadline") or "").lower()
        if any(w in alt for w in ("liveblog", "live-ticker", "liveticker", "live blog")):
            return "liveblog"
        return "standard"

    @staticmethod
    def _strip_html(text: str) -> str:
        """Remove any HTML tags from articleBody and normalize whitespace."""
        clean = BeautifulSoup(text, "html.parser").get_text(separator=" ")
        return " ".join(clean.split())

    @staticmethod
    def _trafilatura_fallback(html: str, url: str) -> str:
        """Last resort: extract body text via trafilatura."""
        import trafilatura
        text = trafilatura.extract(
            html, url=url,
            include_comments=False,
            include_tables=False,
            favor_precision=True,
        )
        return text.strip() if text else ""

    # ------------------------------------------------------------------
    # Pipeline
    # ------------------------------------------------------------------

    def get_articles(self, max_articles: Optional[int] = None, **kwargs) -> list[Article]:
        articles = []
        seen_urls: set[str] = set()

        for index_url in self.index_urls:
            if max_articles and len(articles) >= max_articles:
                break
            try:
                html = self.fetch_html(index_url)
            except Exception as e:
                print(f"[20min] Failed to fetch index {index_url}: {e}")
                continue

            links = self.extract_article_links(html, index_url)
            print(f"[20min] {len(links)} links found on {index_url}")

            for url in links:
                if max_articles and len(articles) >= max_articles:
                    break
                if url in seen_urls:
                    continue
                seen_urls.add(url)
                time.sleep(self._crawl_delay)

                try:
                    article_html = self.fetch_html(url)
                    article = self.parse_article(article_html, url)
                    if article.title and article.content:
                        articles.append(article)
                        print(f"[20min] OK  {article.title[:70]}")
                    else:
                        print(f"[20min] SKIP (no title/content): {url}")
                except Exception as e:
                    print(f"[20min] FAIL {url}: {e}")

        print(f"[20min] Done — {len(articles)} articles collected.")
        return articles
