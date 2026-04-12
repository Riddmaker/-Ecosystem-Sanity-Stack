"""
Base class for all web scraper-based news connectors.
"""

from abc import ABC, abstractmethod
from typing import Optional

from src.connectors.abstract.models import Article



class BaseScraperConnector(ABC):
    """
    Abstract base class for scraper-based news connectors.

    Subclasses must implement:
        - index_urls: list of pages to scrape for article links
        - extract_article_links(): pull article URLs from an index page
        - parse_article(): scrape and normalize a single article page into an Article
    """

    @property
    @abstractmethod
    def index_urls(self) -> list[str]:
        """Return the list of index/section URLs to scrape for article links."""
        ...

    @abstractmethod
    def extract_article_links(self, html: str, index_url: str) -> list[str]:
        """
        Extract article URLs from the raw HTML of an index page.
        Returns a list of absolute URLs.
        """
        ...

    @abstractmethod
    def parse_article(self, html: str, url: str) -> Article:
        """
        Scrape and parse a single article page into a normalized Article.
        """
        ...

    def fetch_html(self, url: str, headers: Optional[dict] = None) -> str:
        """
        Fetch raw HTML from a URL.
        Override to add session management, rotating proxies, etc.
        """
        import requests

        default_headers = {
            "User-Agent": (
                "Mozilla/5.0 (compatible; EcosystemSanityBot/0.1; "
                "+https://github.com/Riddmaker/-Ecosystem-Sanity-Stack)"
            )
        }
        response = requests.get(url, headers={**default_headers, **(headers or {})}, timeout=15)
        response.raise_for_status()
        return response.text

    def get_articles(self, **kwargs) -> list[Article]:
        """
        Full scrape pipeline: index pages -> article links -> parsed articles.
        """
        articles = []
        for index_url in self.index_urls:
            html = self.fetch_html(index_url)
            links = self.extract_article_links(html, index_url)
            for link in links:
                try:
                    article_html = self.fetch_html(link)
                    articles.append(self.parse_article(article_html, link))
                except Exception as e:
                    print(f"[ScraperConnector] Failed to scrape {link}: {e}")
        return articles
