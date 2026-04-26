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

import re
from typing import Optional
from urllib.parse import urljoin

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
        self._session = self._init_session()

    @property
    def index_urls(self) -> list[str]:
        return [BASE_URL + s for s in self._sections]

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
        news_article, breadcrumb_items, _ = self._parse_json_ld(soup)

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

    # ------------------------------------------------------------------
    # Watson-specific helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_article_id(url: str) -> Optional[str]:
        """Extract numeric article ID from watson URL (first segment of last path part)."""
        match = re.search(r"/(\d{6,})-", url)
        return match.group(1) if match else None

    @staticmethod
    def _parse_breadcrumb(items: list) -> tuple[Optional[str], list[str]]:
        """
        Watson structure: Section > Subsection/Tag > Article title — skip last item.
        """
        crumbs = [
            item.get("name", "").strip()
            for item in items[:-1]
            if item.get("name", "").strip()
        ]
        return (crumbs[0] if crumbs else None), crumbs[1:]
