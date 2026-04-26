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

import re
from typing import Optional
from urllib.parse import urljoin

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
        self._session = self._init_session()

    @property
    def index_urls(self) -> list[str]:
        return [urljoin(BASE_URL, section) for section in self._sections]

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
        soup = BeautifulSoup(html, "html.parser")
        news_article, breadcrumb, _ = self._parse_json_ld(soup)

        content = self._strip_html(news_article.get("articleBody", ""))
        if not content:
            content = self._trafilatura_fallback(html, url)

        alternative_headline = news_article.get("alternativeHeadline", "").strip()
        if alternative_headline:
            content = f"[Unterzeile: {alternative_headline}]\n\n{content}"

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

    # ------------------------------------------------------------------
    # 20min-specific helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_article_id(url: str) -> str | None:
        """Extract the numeric article ID from the end of a 20min /story/ URL."""
        match = re.search(r"-(\d{6,12})$", url.rstrip("/").split("?")[0])
        return match.group(1) if match else None

    @staticmethod
    def _detect_article_type(news_article: dict) -> str:
        """Guess article type from JSON-LD fields."""
        if news_article.get("liveBlogUpdate") or news_article.get("@type") == "LiveBlogPosting":
            return "liveblog"
        alt = (news_article.get("alternativeHeadline") or "").lower()
        if any(w in alt for w in ("liveblog", "live-ticker", "liveticker", "live blog")):
            return "liveblog"
        return "standard"

    @staticmethod
    def _parse_breadcrumb(items: list) -> tuple[Optional[str], list[str]]:
        """
        20min structure: News > Category > Subcategory > Article title (last item skipped).
        Filters out the generic "News" root crumb.
        """
        crumbs = []
        for item in items[:-1]:
            name = item.get("item", {}).get("name") or item.get("name", "")
            if name and name.lower() != "news":
                crumbs.append(name)
        return (crumbs[0] if crumbs else None), crumbs[1:]
