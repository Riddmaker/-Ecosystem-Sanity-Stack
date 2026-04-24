"""
Abstract base classes for web scraper-based news connectors.

Hierarchy
─────────
BaseScraperConnector          — shared utilities + HTTP (requests) pipeline
└── BasePlaywrightScraperConnector  — same interface, Playwright browser lifecycle

Concrete HTTP scrapers  (watson, 20min, nau) extend BaseScraperConnector.
Concrete PW scrapers    (blick)              extend BasePlaywrightScraperConnector.
"""

import json
import time
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Optional

import requests
from bs4 import BeautifulSoup

from src.connectors.abstract.models import Article


# ─────────────────────────────────────────────────────────────────────────────
# Shared base
# ─────────────────────────────────────────────────────────────────────────────

class BaseScraperConnector(ABC):
    """
    Abstract base for HTTP-based scraper connectors.

    Subclasses MUST define:
        SOURCE           — class-level str, e.g. "watson.ch"
        LANGUAGE         — class-level str (default "de")
        index_urls       — property returning list of section URLs to crawl
        extract_article_links(html, index_url) → list[str]
        parse_article(html, url)               → Article
        _extract_article_id(url)               → Optional[str]

    Subclasses MAY override:
        fetch_html(url)                        — default: requests.Session
        _parse_breadcrumb(items)               — default: skip Home + last crumb
        _parse_author(author)                  — default: handles dict/list/str
        get_articles(...)                      — default: full HTTP pipeline

    Shared utilities (static, ready to use in any subclass):
        _parse_json_ld(soup)     → (news_article, breadcrumb_items, author_name)
        _parse_datetime(value)   → datetime
        _trafilatura_fallback(html, url) → str
        _strip_html(text)        → str
    """

    SOURCE: str = ""
    LANGUAGE: str = "de"

    # ------------------------------------------------------------------
    # Abstract interface
    # ------------------------------------------------------------------

    @property
    @abstractmethod
    def index_urls(self) -> list[str]:
        """Section/index pages to crawl for article links."""

    @abstractmethod
    def extract_article_links(self, html: str, index_url: str) -> list[str]:
        """Return absolute article URLs found in the HTML of an index page."""

    @abstractmethod
    def parse_article(self, html: str, url: str) -> Article:
        """Parse a single article page into a normalised Article."""

    @staticmethod
    @abstractmethod
    def _extract_article_id(url: str) -> Optional[str]:
        """Extract a site-specific article ID from its URL."""

    # ------------------------------------------------------------------
    # HTTP fetching (override in Playwright subclass)
    # ------------------------------------------------------------------

    def fetch_html(self, url: str) -> str:
        """Fetch raw HTML via requests. Override for bot-protected sites."""
        response = self._session.get(url, timeout=15)
        response.raise_for_status()
        return response.text

    def _init_session(
        self,
        extra_headers: Optional[dict] = None,
    ) -> requests.Session:
        """Create a requests.Session with a realistic browser UA. Call in __init__."""
        session = requests.Session()
        session.headers.update({
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            "Accept-Language": "de-CH,de;q=0.9",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        })
        if extra_headers:
            session.headers.update(extra_headers)
        return session

    # ------------------------------------------------------------------
    # Shared JSON-LD utilities
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_json_ld(
        soup: BeautifulSoup,
    ) -> tuple[dict, list, Optional[str]]:
        """
        Parse all JSON-LD blocks in one pass.

        Returns:
            news_article     — dict for the first NewsArticle/Article block found
            breadcrumb_items — list from the first BreadcrumbList block found
            author_name      — name from the first standalone Person block (or None)
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
                elif t == "WebPage":
                    # Some sites put datePublished/description only on WebPage
                    if block.get("datePublished") and not news_article.get("datePublished"):
                        news_article.setdefault("datePublished", block["datePublished"])
                    if block.get("description") and not news_article.get("description"):
                        news_article.setdefault("description", block["description"])
                elif t == "BreadcrumbList" and not breadcrumb_items:
                    breadcrumb_items = block.get("itemListElement", [])
                elif t == "Person" and not author_name:
                    author_name = block.get("name")

            if news_article and breadcrumb_items:
                break

        return news_article, breadcrumb_items, author_name

    @staticmethod
    def _parse_breadcrumb(items: list) -> tuple[Optional[str], list[str]]:
        """
        Extract (category, tags) from a BreadcrumbList itemListElement.

        Default: strips leading "Home" crumb and the last crumb (article title).
        Override per site if the structure differs.
        """
        crumbs = []
        for item in items:
            name = (
                item.get("name")
                or item.get("item", {}).get("name")
                or ""
            ).strip()
            if name and name.lower() != "home":
                crumbs.append(name)
        # Last crumb is usually the article title — drop it
        if len(crumbs) > 1:
            crumbs = crumbs[:-1]
        return (crumbs[0] if crumbs else None), crumbs[1:]

    @staticmethod
    def _parse_author(author) -> Optional[str]:
        """
        Normalise the author field from JSON-LD.

        Handles: dict, list[dict], list[list[dict]] (nau.ch quirk), str.
        """
        if not author:
            return None
        # Unwrap nested lists: [[{...}]] → [{...}]
        while isinstance(author, list):
            if not author:
                return None
            if isinstance(author[0], list):
                author = author[0]
            elif isinstance(author[0], dict):
                return author[0].get("name")
            else:
                return str(author[0])
        if isinstance(author, dict):
            return author.get("name")
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
    def _trafilatura_fallback(html: str, url: str) -> str:
        import trafilatura
        text = trafilatura.extract(
            html, url=url,
            include_comments=False,
            include_tables=False,
            favor_precision=True,
        )
        return text.strip() if text else ""

    @staticmethod
    def _strip_html(text: str) -> str:
        clean = BeautifulSoup(text, "html.parser").get_text(separator=" ")
        return " ".join(clean.split())

    # ------------------------------------------------------------------
    # Full HTTP pipeline — override completely in Playwright subclass
    # ------------------------------------------------------------------

    def get_articles(
        self,
        max_articles: Optional[int] = None,
        since: Optional[datetime] = None,
        max_consecutive_old: int = 3,
        **kwargs,
    ) -> list[Article]:
        """
        Crawl all index_urls, follow article links, return parsed Articles.

        Args:
            max_articles:        Hard cap on total articles returned.
            since:               Skip articles older than this datetime.
            max_consecutive_old: Abort a section after N consecutive old articles.
        """
        tag = f"[{self.SOURCE or self.__class__.__name__}]"
        articles: list[Article] = []
        seen_urls: set[str] = set()

        for index_url in self.index_urls:
            if max_articles and len(articles) >= max_articles:
                break
            try:
                html = self.fetch_html(index_url)
            except Exception as e:
                print(f"{tag} Failed to fetch index {index_url}: {e}")
                continue

            links = self.extract_article_links(html, index_url)
            print(f"{tag} {len(links)} links found on {index_url}")

            consecutive_old = 0

            for url in links:
                if max_articles and len(articles) >= max_articles:
                    break
                if url in seen_urls:
                    continue
                seen_urls.add(url)

                if hasattr(self, "_crawl_delay"):
                    time.sleep(self._crawl_delay)

                try:
                    article_html = self.fetch_html(url)
                    article = self.parse_article(article_html, url)

                    if not article.title or not article.content:
                        print(f"{tag} SKIP (no title/content): {url}")
                        continue

                    if since is not None:
                        pub = article.published_at
                        if pub.tzinfo is None:
                            pub = pub.replace(tzinfo=timezone.utc)
                        if pub < since:
                            consecutive_old += 1
                            print(
                                f"{tag} OLD ({consecutive_old}/{max_consecutive_old})"
                                f"  {pub.strftime('%H:%M')}  {article.title[:60]}"
                            )
                            if consecutive_old >= max_consecutive_old:
                                print(
                                    f"{tag} {max_consecutive_old} consecutive old"
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
                    print(f"{tag} OK   {pub_str}  {article.title[:60]}")

                except Exception as e:
                    print(f"{tag} FAIL {url}: {e}")

        print(f"{tag} Done — {len(articles)} articles collected.")
        return articles


# ─────────────────────────────────────────────────────────────────────────────
# Playwright base
# ─────────────────────────────────────────────────────────────────────────────

class BasePlaywrightScraperConnector(BaseScraperConnector):
    """
    Abstract base for Playwright-based scraper connectors.

    Inherits all shared utilities from BaseScraperConnector.
    Overrides get_articles() to manage a single browser session across the
    entire scrape — required for sites with bot protection (e.g. Akamai).

    Subclasses must still implement:
        index_urls, extract_article_links(), parse_article(), _extract_article_id()

    Subclasses may override:
        _pw_wait_after_load   — ms to wait after domcontentloaded on index pages
        _pw_wait_after_article — ms to wait after domcontentloaded on article pages
    """

    _pw_wait_after_load: int    = 2000   # ms — index pages
    _pw_wait_after_article: int = 1500   # ms — article pages

    def fetch_html(self, url: str) -> str:
        """Not used in Playwright scrapers — browser manages fetching in get_articles()."""
        raise NotImplementedError(
            "Playwright scrapers fetch pages inside get_articles(). "
            "Do not call fetch_html() directly."
        )

    def get_articles(
        self,
        max_articles: Optional[int] = None,
        since: Optional[datetime] = None,
        max_consecutive_old: int = 3,
        **kwargs,
    ) -> list[Article]:
        """
        Crawl all index_urls via a single Playwright browser session.

        Opens one Chromium instance, reuses one Page object throughout,
        then closes everything cleanly.
        """
        from playwright.sync_api import sync_playwright, Browser, Page

        tag = f"[{self.SOURCE or self.__class__.__name__}]"
        articles: list[Article] = []
        seen_urls: set[str] = set()

        with sync_playwright() as pw:
            browser: Browser = pw.chromium.launch(headless=True)
            page: Page = browser.new_page()

            for index_url in self.index_urls:
                if max_articles and len(articles) >= max_articles:
                    break
                try:
                    page.goto(index_url, wait_until="domcontentloaded", timeout=30_000)
                    page.wait_for_timeout(self._pw_wait_after_load)
                    html = page.content()
                except Exception as e:
                    print(f"{tag} Failed to fetch index {index_url}: {e}")
                    continue

                links = self.extract_article_links(html, index_url)
                print(f"{tag} {len(links)} links found on {index_url}")

                consecutive_old = 0

                for url in links:
                    if max_articles and len(articles) >= max_articles:
                        break
                    if url in seen_urls:
                        continue
                    seen_urls.add(url)

                    if hasattr(self, "_crawl_delay"):
                        time.sleep(self._crawl_delay)

                    try:
                        page.goto(url, wait_until="domcontentloaded", timeout=30_000)
                        page.wait_for_timeout(self._pw_wait_after_article)
                        article_html = page.content()
                        article = self.parse_article(article_html, url)

                        if not article.title or not article.content:
                            print(f"{tag} SKIP (no title/content): {url}")
                            continue

                        if since is not None:
                            pub = article.published_at
                            if pub.tzinfo is None:
                                pub = pub.replace(tzinfo=timezone.utc)
                            if pub < since:
                                consecutive_old += 1
                                print(
                                    f"{tag} OLD ({consecutive_old}/{max_consecutive_old})"
                                    f"  {pub.strftime('%H:%M')}  {article.title[:60]}"
                                )
                                if consecutive_old >= max_consecutive_old:
                                    print(
                                        f"{tag} {max_consecutive_old} consecutive old"
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
                        print(f"{tag} OK   {pub_str}  {article.title[:60]}")

                    except Exception as e:
                        print(f"{tag} FAIL {url}: {e}")

            browser.close()

        print(f"{tag} Done — {len(articles)} articles collected.")
        return articles
