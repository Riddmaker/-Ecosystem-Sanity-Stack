"""
Blick.ch — Scraper connector.

Extracts articles from www.blick.ch using Playwright (required: Akamai bot
protection blocks plain HTTP requests).

Strategy:
  - Index pages: launch Playwright, extract /-id\\d+\\.html links
  - Content:     <p> tags inside <article> element (no articleBody in JSON-LD)
  - Metadata:    NewsArticle + WebPage JSON-LD blocks (headline, datePublished,
                 description), Person block for author name
  - Category:    BreadcrumbList JSON-LD block
  - Fallback:    trafilatura if <p> extraction yields nothing

Dependencies:
    pip install playwright beautifulsoup4 trafilatura
    playwright install chromium
"""

import json
import re
import time
from datetime import datetime, timezone
from typing import Optional

from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright, Browser, Page

from src.connectors.abstract.models import Article
from src.connectors.abstract.scraper_connector import BaseScraperConnector


BASE_URL = "https://www.blick.ch"

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

CRAWL_DELAY = 1.5   # seconds between article fetches — be respectful

# Pattern that matches article URLs (ends with -id<digits>.html)
ARTICLE_URL_RE = re.compile(r"-id\d{6,12}\.html$")

# Only collect links from these top-level sections (avoids podcasts, impressum, etc.)
NEWS_SECTIONS = {
    "schweiz", "ausland", "politik", "wirtschaft", "gesellschaft",
    "sport", "digital", "life", "people-tv", "meinung", "wetter",
}


class BlickScraperConnector(BaseScraperConnector):
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

    def __init__(
        self,
        sections: Optional[list[str]] = None,
        crawl_delay: float = CRAWL_DELAY,
    ):
        self._sections = sections or DEFAULT_SECTIONS
        self._crawl_delay = crawl_delay

    # ------------------------------------------------------------------
    # Index page
    # ------------------------------------------------------------------

    @property
    def index_urls(self) -> list[str]:
        return [BASE_URL + s for s in self._sections]

    def extract_article_links(self, html: str, index_url: str = "") -> list[str]:
        """Extract unique article URLs from a listing page, restricted to news sections."""
        soup = BeautifulSoup(html, "html.parser")
        seen: set[str] = set()
        links: list[str] = []
        for tag in soup.find_all("a", href=ARTICLE_URL_RE):
            href = tag["href"].split("?")[0]
            if not href.startswith("http"):
                href = BASE_URL + href
            # Only include URLs whose top-level section is a known news section
            path = href.replace(BASE_URL, "").lstrip("/")
            top_section = path.split("/")[0]
            if top_section not in NEWS_SECTIONS:
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
            author=author_name,
            category=category,
            tags=tags,
            word_count=len(content.split()) if content else None,
            article_type="standard",
            connector_type="scraper",
            raw=news_article,
        )

    def _parse_json_ld(self, soup: BeautifulSoup) -> tuple[dict, list, Optional[str]]:
        """
        Parse all JSON-LD blocks in one pass.
        Returns (NewsArticle dict, BreadcrumbList items, author name).
        """
        news_article: dict = {}
        breadcrumb_items: list = []
        author_name: Optional[str] = None

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
                elif t == "WebPage" and not news_article.get("datePublished"):
                    # WebPage sometimes has datePublished when NewsArticle doesn't
                    if block.get("datePublished"):
                        news_article.setdefault("datePublished", block["datePublished"])
                    if block.get("description") and not news_article.get("description"):
                        news_article.setdefault("description", block["description"])
                elif t == "BreadcrumbList" and not breadcrumb_items:
                    breadcrumb_items = block.get("itemListElement", [])
                elif t == "Person" and not author_name:
                    author_name = block.get("name")

        return news_article, breadcrumb_items, author_name

    @staticmethod
    def _extract_article_body(soup: BeautifulSoup) -> str:
        """
        Extract article text from <p> tags within <article>.
        Filters out very short fragments (captions, labels).
        """
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
        """
        Extract category and tags from BreadcrumbList.
        Structure: Home > Category > (Subcategory) > Article title
        Skip 'Home' and the last item (article title).
        """
        crumbs = []
        for item in items[1:-1]:   # skip Home (first) and article title (last)
            name = item.get("name", "").strip()
            if name:
                crumbs.append(name)
        return (crumbs[0] if crumbs else None), crumbs[1:]

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
        match = re.search(r"-id(\d{6,12})\.html", url)
        return match.group(1) if match else None

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
    # Pipeline — manages a single Playwright browser session
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

        with sync_playwright() as pw:
            browser: Browser = pw.chromium.launch(headless=True)
            page: Page = browser.new_page()

            for section in self._sections:
                if max_articles and len(articles) >= max_articles:
                    break

                index_url = BASE_URL + section
                try:
                    page.goto(index_url, wait_until="domcontentloaded", timeout=30000)
                    page.wait_for_timeout(2000)
                    html = page.content()
                except Exception as e:
                    print(f"[blick] Failed to fetch index {index_url}: {e}")
                    continue

                links = self.extract_article_links(html)
                print(f"[blick] {len(links)} links found on {index_url}")

                consecutive_old = 0

                for url in links:
                    if max_articles and len(articles) >= max_articles:
                        break
                    if url in seen_urls:
                        continue
                    seen_urls.add(url)
                    time.sleep(self._crawl_delay)

                    try:
                        page.goto(url, wait_until="domcontentloaded", timeout=30000)
                        page.wait_for_timeout(1500)
                        article_html = page.content()
                        article = self.parse_article(article_html, url)

                        if not article.title or not article.content:
                            print(f"[blick] SKIP (no title/content): {url}")
                            continue

                        if since is not None:
                            pub = article.published_at
                            if pub.tzinfo is None:
                                pub = pub.replace(tzinfo=timezone.utc)
                            if pub < since:
                                consecutive_old += 1
                                print(
                                    f"[blick] OLD ({consecutive_old}/{max_consecutive_old})"
                                    f"  {pub.strftime('%H:%M')}  {article.title[:60]}"
                                )
                                if consecutive_old >= max_consecutive_old:
                                    print(
                                        f"[blick] {max_consecutive_old} consecutive old"
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
                        print(f"[blick] OK   {pub_str}  {article.title[:60]}")

                    except Exception as e:
                        print(f"[blick] FAIL {url}: {e}")

            browser.close()

        print(f"[blick] Done — {len(articles)} articles collected.")
        return articles
