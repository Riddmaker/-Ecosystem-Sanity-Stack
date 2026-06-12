"""
Base class for all RSS-based news connectors.
"""

import logging
from abc import ABC, abstractmethod

from src.connectors.abstract.models import Article

log = logging.getLogger(__name__)


class BaseRSSConnector(ABC):
    """
    Abstract base class for RSS feed-based news connectors.

    Subclasses must implement:
        - feed_urls: list of RSS feed URLs to poll
        - parse_entry(): normalize a raw feedparser entry into an Article
    """

    @property
    @abstractmethod
    def feed_urls(self) -> list[str]:
        """Return the list of RSS feed URLs this connector polls."""
        ...

    @abstractmethod
    def parse_entry(self, entry: dict) -> Article:
        """
        Parse a single feedparser entry dict into a normalized Article.
        """
        ...

    def get_articles(self, **kwargs) -> list[Article]:
        """
        Fetch and parse all entries from all configured feed URLs.
        Requires feedparser to be installed.
        """
        import feedparser

        articles = []
        for url in self.feed_urls:
            feed = feedparser.parse(url)
            for entry in feed.entries:
                try:
                    articles.append(self.parse_entry(entry))
                except Exception as e:
                    # log and continue — one bad entry shouldn't abort the run
                    log.warning("[RSSConnector] Failed to parse entry: %s", e)
        return articles
