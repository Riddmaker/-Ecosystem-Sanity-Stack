"""
Shared data models for all connectors.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class Article:
    """Normalized article representation across all connectors."""
    # Required
    title: str
    url: str
    content: str
    published_at: datetime
    source: str

    # Optional provenance
    source_article_id: Optional[str] = None   # e.g. "103543041" from 20min URL
    language: str = "de"
    author: Optional[str] = None
    category: Optional[str] = None
    tags: list[str] = field(default_factory=list)
    summary: Optional[str] = None

    # Computed at scrape time
    word_count: Optional[int] = None
    article_type: str = "standard"            # standard | liveblog | opinion | sponsored
    connector_type: str = "scraper"           # scraper | rss | api

    raw: Optional[dict] = None
