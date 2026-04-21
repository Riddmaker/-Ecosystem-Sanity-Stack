"""
Watson.ch — Scraper connector.

Extracts articles directly from www.watson.ch via plain HTTP requests
(no bot protection — same strategy as the 20min connector).

Strategy:
  - Index pages: extract article links via numeric-ID URL pattern
  - Content:     articleBody field from JSON-LD NewsArticle schema
  - Metadata:    headline, description, datePublished, author from same block
  - Category:    BreadcrumbList JSON-LD block
  - Fallback:    trafilatura if articleBody is missing

URL pattern:  /section/subsection/NUMERIC_ID-slug  (no .html extension)

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


BASE_URL = "https://www.watson.ch"

DEFAULT_SECTIONS = [
    "/schweiz/",
    "/international/",
    "/wirtschaft/",
    "/sport/",
    "/wissen/",
    "/digital/",
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

# Article URLs: last path segment starts with a numeric ID followed by a dash
ARTICLE_URL_RE = re.compile(r"/\d{6,}-[a-z]")


class WatsonScraperConnector(BaseScraperConnector):
    """
    Scrapes articles from www.watson.ch.

    Usage:
        connector = WatsonScraperConnector()
        articles = connector.get_articles()

        connector = WatsonScraperConnector(sections=["/schweiz/", "/international/"])
        articles = connector.get_articles(max_articles=20)
    """

    SOURCE = "watson.ch"
    LANGUAGE = "de"

    def __init__(
        self,
        sections: Optional[list[str]] = None,
        crawl_delay: float = CRAWL_DELAY,
    ):
        self._sections = sections or DEFAULT_SECTIONS
        self._crawl_delay = crawl_delay
        self._session = requests.Session()
        self._session.headers.update(HEADERS)

    @property
    def index_urls(self) -> list[str]:
        return [BASE_URL + s for s in self._sections]

    def fetch_html(self, url: str, headers: Optional[dict] = None) -> str:
        response = self._session.get(url, headers=headers or {}, timeout=15)
        response.raise_for_status()
        return response.text

    # ------------------------------------------------------------------
    # Index page
    # ------------------------------------------------------------------

    def extract_article_links(self, html: str, index_url: str = "") -> list[str]:
        """Extract unique article URLs from a listing page."""
        soup = BeautifulSoup(html, "html.parser")
        seen: set[str] = set()
        links: list[str] = []
        for tag in soup.find_all("a", href=ARTICLE_URL_RE):
            href = tag["href"].split("?")[0]
            if not href.startswith("http"):
                href = urljoin(BASE_URL, href)
            # Only watson.ch URLs, no external links
            if not href.startswith(BASE_URL):
                continue
            if href not in seen:
                seen.add(href)
                links.append(href)
        return links

    # ------------------------------------------------------------------
    # Article page
    # ------------------------------------------------------------------

    def parse_article(self, html: str, url: str) -> Article:
        soup = BeautifulSoup(html, "html.parser")
        news_article, breadcrumb_items = self._parse_json_ld(soup)

        content = self._strip_html(news_article.get("articleBody", ""))
        if not content:
            content = self._trafilatura_fallback(html, url)

        description = (news_article.get("description") or "").strip()
        if description and content:
            content = f"[Lead: {description}]\n\n{content}"

        category, tags = self._parse_breadcrumb(breadcrumb_items)

        return Article(
            title=(news_article.get("headline") or "").strip(),
            url=url,
            source_article_id=self._extract_article_id(url),
            content=content,
            summary=description or None,
            published_at=self._parse_datetime(news_article.get("datePublished")),
            source=self.SOURCE,
            language=self.LANGUAGE,
            author=self._parse_author(news_article.get("author")),
            category=category,
            tags=tags,
            word_count=len(content.split()) if content else None,
            article_type="standard",
            connector_type="scraper",
            raw=news_article,
        )

    def _parse_json_ld(self, soup: BeautifulSoup) -> tuple[dict, list]:
        """Parse NewsArticle and BreadcrumbList JSON-LD blocks in one pass."""
        news_article: dict = {}
        breadcrumb_items: list = []

        for script in soup.find_all("script", type="application/ld+json"):
            try:
                data = json.loads(script.string or "")
            except (json.JSONDecodeError, AttributeError):
                continue

            if isinstance(data, list):
                blocks = data
            elif "@graph" in data:
                blocks = data["@graph"]
            else:
                blocks = [data]

            for block in blocks:
                t = block.get("@type")
                if t in ("NewsArticle", "Article") and not news_article:
                    news_article = block
                elif t == "BreadcrumbList" and not breadcrumb_items:
                    breadcrumb_items = block.get("itemListElement", [])

            if news_article and breadcrumb_items:
                break

        return news_article, breadcrumb_items

    @staticmethod
    def _parse_breadcrumb(items: list) -> tuple[Optional[str], list[str]]:
        """
        Extract category and tags from BreadcrumbList.
        Watson structure: Section > Subsection/Tag > Article title
        Skip the last item (article title).
        """
        crumbs = [
            item.get("name", "").strip()
            for item in items[:-1]
            if item.get("name", "").strip()
        ]
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
    def _extract_article_id(url: str) -> Optional[str]:
        """Extract numeric article ID from watson URL (first segment of last path part)."""
        match = re.search(r"/(\d{6,})-", url)
        return match.group(1) if match else None

    @staticmethod
    def _strip_html(text: str) -> str:
        clean = BeautifulSoup(text, "html.parser").get_text(separator=" ")
        return " ".join(clean.split())

    @staticmethod
    def _trafilatura_fallback(html: str, url: str) -> str:
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

    def get_articles(
        self,
        max_articles: Optional[int] = None,
        since: Optional[datetime] = None,
        max_consecutive_old: int = 3,
        **kwargs,
    ) -> list[Article]:
        """
        Scrape articles from all configured sections.

        Args:
            max_articles:        Hard cap on total articles returned.
            since:               Skip articles older than this datetime.
            max_consecutive_old: Stop a section after this many consecutive
                                 old articles (index pages are newest-first).
        """
        articles: list[Article] = []
        seen_urls: set[str] = set()

        for index_url in self.index_urls:
            if max_articles and len(articles) >= max_articles:
                break
            try:
                html = self.fetch_html(index_url)
            except Exception as e:
                print(f"[watson] Failed to fetch index {index_url}: {e}")
                continue

            links = self.extract_article_links(html, index_url)
            print(f"[watson] {len(links)} links found on {index_url}")

            consecutive_old = 0

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

                    if not article.title or not article.content:
                        print(f"[watson] SKIP (no title/content): {url}")
                        continue

                    if since is not None:
                        pub = article.published_at
                        if pub.tzinfo is None:
                            pub = pub.replace(tzinfo=timezone.utc)
                        if pub < since:
                            consecutive_old += 1
                            print(
                                f"[watson] OLD ({consecutive_old}/{max_consecutive_old})"
                                f"  {pub.strftime('%H:%M')}  {article.title[:60]}"
                            )
                            if consecutive_old >= max_consecutive_old:
                                print(
                                    f"[watson] {max_consecutive_old} consecutive old"
                                    f" articles — stopping section."
                                )
                                break
                            continue

                    consecutive_old = 0
                    articles.append(article)
                    pub_str = (
                        article.published_at.strftime("%H:%M")
                        if article.published_at else "?"
                    )
                    print(f"[watson] OK   {pub_str}  {article.title[:60]}")

                except Exception as e:
                    print(f"[watson] FAIL {url}: {e}")

        print(f"[watson] Done — {len(articles)} articles collected.")
        return articles
