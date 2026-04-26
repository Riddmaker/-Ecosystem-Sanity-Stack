"""
Base class for all API-based news connectors.
"""

from abc import ABC, abstractmethod

from src.connectors.abstract.models import Article


class BaseAPIConnector(ABC):
    """
    Abstract base class for REST API-based news connectors.

    Subclasses must implement:
        - fetch_articles(): retrieve a list of raw articles from the API
        - parse_article(): normalize a raw API response into an Article
    """

    def __init__(self, api_key: str):
        self.api_key = api_key

    @abstractmethod
    def fetch_articles(self, **kwargs) -> list[Article]:
        """
        Fetch articles from the API.

        Returns a list of normalized Article objects.
        kwargs can carry source-specific parameters (e.g. category, page, limit).
        """
        ...

    @abstractmethod
    def parse_article(self, raw: dict) -> Article:
        """
        Parse a single raw API response dict into a normalized Article.
        """
        ...

    def get_articles(self, **kwargs) -> list[Article]:
        """
        Public entry point. Fetches and returns articles.
        Override for pre/post-processing hooks if needed.
        """
        return self.fetch_articles(**kwargs)
