"""
Nau.ch — Scraper connector.

Extracts articles from www.nau.ch via plain HTTP requests.

Strategy:
  - Index pages:  extract article links via numeric-ID URL pattern
  - Metadata:     headline, description, datePublished, author from JSON-LD NewsArticle
  - Content:      trafilatura (no articleBody in JSON-LD)
  - Category:     BreadcrumbList JSON-LD block

URL pattern:  /section/subsection/slug-NUMERIC_ID

Dependencies:
    pip install requests beautifulsoup4 trafilatura
"""

import re
from typing import Optional
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from src.connectors.abstract.models import Article
from src.connectors.abstract.scraper_connector import BaseScraperConnector


BASE_URL = "https://www.nau.ch"

DEFAULT_SECTIONS = [
    "/news",
    "/news/ausland",
    "/news/europa",
    "/news/wirtschaft",
    "/news/digital",
    "/news/forschung",
    "/politik",
    "/sport",
    "/people",
]

CRAWL_DELAY = 1.0

# Article URLs: path ends with a slug followed by a numeric ID (7–8 digits)
ARTICLE_URL_RE = re.compile(r"/[a-z0-9-]+-\d{7,}$")


class NauScraperConnector(BaseScraperConnector):
    """
    Scrapes articles from www.nau.ch.

    Usage:
        connector = NauScraperConnector()
        articles = connector.get_articles()

        connector = NauScraperConnector(sections=["/news", "/politik"])
        articles = connector.get_articles(max_articles=20)
    """

    SOURCE = "nau.ch"
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
        for tag in soup.find_all("a", href=True):
            href = tag["href"].split("?")[0].rstrip("/")
            if not ARTICLE_URL_RE.search(href):
                continue
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

        content = self._trafilatura_fallback(html, url)

        description = (news_article.get("description") or "").strip()
        if description and content and not content.startswith(description[:40]):
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
    # Nau-specific helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_article_id(url: str) -> Optional[str]:
        """Extract numeric article ID from the end of a nau.ch URL."""
        match = re.search(r"-(\d{7,})$", url)
        return match.group(1) if match else None

    @staticmethod
    def _parse_breadcrumb(items: list) -> tuple[Optional[str], list[str]]:
        """
        Nau breadcrumbs don't include the article title as last item — no trailing skip.
        """
        crumbs = [
            item.get("item", {}).get("name", item.get("name", "")).strip()
            for item in items
            if item.get("item", {}).get("name") or item.get("name")
        ]
        crumbs = [c for c in crumbs if c.lower() != "home"]
        return (crumbs[0] if crumbs else None), crumbs[1:]
