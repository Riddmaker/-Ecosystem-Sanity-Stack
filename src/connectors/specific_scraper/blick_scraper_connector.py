"""
Blick.ch — Scraper connector.

Extracts articles from www.blick.ch using Playwright (required: Akamai bot
protection blocks plain HTTP requests).

Strategy:
  - Index pages: Playwright, extract /-id\\d+\\.html links
  - Content:     <p> tags inside <article> element; trafilatura fallback
  - Metadata:    NewsArticle + WebPage JSON-LD (headline, datePublished, description)
  - Author:      standalone Person JSON-LD block
  - Category:    BreadcrumbList JSON-LD block

Dependencies:
    pip install playwright beautifulsoup4 trafilatura
    playwright install chromium
"""

import re
from typing import Optional

from bs4 import BeautifulSoup

from src.connectors.abstract.models import Article
from src.connectors.abstract.scraper_connector import BasePlaywrightScraperConnector


BASE_URL = "https://www.blick.ch"

# Article URLs: end with -id<digits>.html
ARTICLE_URL_RE = re.compile(r"-id\d{6,12}\.html$")

# Allowed top-level sections (avoids podcasts, impressum, etc.)
NEWS_SECTIONS = {
    "schweiz", "ausland", "politik", "wirtschaft", "gesellschaft",
    "sport", "digital", "life", "people-tv", "meinung", "wetter",
}


class BlickScraperConnector(BasePlaywrightScraperConnector):
    """
    Scrapes articles from www.blick.ch via Playwright.

    Usage:
        connector = BlickScraperConnector()
        articles = connector.get_articles()

        connector = BlickScraperConnector(sections=["/politik/", "/wirtschaft/"])
        articles = connector.get_articles(max_articles=20)
    """

    SOURCE = "blick.ch"
    LANGUAGE = "de"
    BASE_URL = BASE_URL
    CRAWL_DELAY = 1.5
    DEFAULT_SECTIONS = [
        "/schweiz/",
        "/ausland/",
        "/politik/",
        "/wirtschaft/",
        "/gesellschaft/",
        "/sport/",
        "/digital/",
        "/life/",
    ]

    # ------------------------------------------------------------------
    # Index page
    # ------------------------------------------------------------------

    def extract_article_links(self, html: str, index_url: str = "") -> list[str]:
        """Extract unique article URLs, restricted to known news sections."""
        soup = BeautifulSoup(html, "html.parser")
        seen: set[str] = set()
        links: list[str] = []
        for tag in soup.find_all("a", href=ARTICLE_URL_RE):
            href = tag["href"].split("?")[0]
            if not href.startswith("http"):
                href = BASE_URL + href
            path = href.replace(BASE_URL, "").lstrip("/")
            if path.split("/")[0] not in NEWS_SECTIONS:
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
        news_article, breadcrumb_items, author_name = self._parse_json_ld(soup)

        title = (
            news_article.get("headline")
            or self._og_meta(soup, "og:title")
            or ""
        ).strip()

        description = (
            news_article.get("description")
            or self._og_meta(soup, "og:description")
            or ""
        ).strip()

        content = self._extract_article_body(soup)
        if not content:
            content = self._trafilatura_fallback(html, url)
        if description and content:
            content = f"[Lead: {description}]\n\n{content}"

        category, tags = self._parse_breadcrumb(breadcrumb_items)

        return Article(
            title=title,
            url=url,
            source_article_id=self._extract_article_id(url),
            content=content,
            summary=description or None,
            published_at=self._parse_datetime(news_article.get("datePublished")),
            source=self.SOURCE,
            language=self.LANGUAGE,
            author=author_name or self._parse_author(news_article.get("author")),
            category=category,
            tags=tags,
            word_count=len(content.split()) if content else None,
            article_type="standard",
            connector_type="scraper",
            raw=news_article,
        )

    # ------------------------------------------------------------------
    # Blick-specific helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_article_id(url: str) -> Optional[str]:
        match = re.search(r"-id(\d{6,12})\.html", url)
        return match.group(1) if match else None

    @staticmethod
    def _extract_article_body(soup: BeautifulSoup) -> str:
        """Extract body text from <p> tags inside <article>."""
        article_el = soup.find("article")
        if not article_el:
            return ""
        paragraphs = [
            p.get_text(separator=" ", strip=True)
            for p in article_el.find_all("p")
            if len(p.get_text(strip=True)) > 40
        ]
        return " ".join(paragraphs)

    @staticmethod
    def _og_meta(soup: BeautifulSoup, property_name: str) -> str:
        tag = soup.find("meta", property=property_name)
        return (tag.get("content") or "") if tag else ""

    @staticmethod
    def _parse_breadcrumb(items: list) -> tuple[Optional[str], list[str]]:
        """Blick structure: Home > Category > (Sub) > Article title — skip first and last."""
        crumbs = [
            item.get("name", "").strip()
            for item in items[1:-1]
            if item.get("name", "").strip()
        ]
        return (crumbs[0] if crumbs else None), crumbs[1:]
