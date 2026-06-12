"""
SQLAlchemy ORM models.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, Float, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class ArticleModel(Base):
    __tablename__ = "articles"

    # Internal key — UUID we generate once, never changes
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    # Source identity — primary dedup key
    source: Mapped[str] = mapped_column(String(100), nullable=False)
    source_article_id: Mapped[str | None] = mapped_column(Text)   # e.g. "103543041"

    # URL — best-effort match fallback, not a hard unique constraint
    url: Mapped[str] = mapped_column(Text, nullable=False)

    # Content
    title: Mapped[str | None] = mapped_column(Text)
    content: Mapped[str | None] = mapped_column(Text)
    summary: Mapped[str | None] = mapped_column(Text)
    word_count: Mapped[int | None] = mapped_column(Integer)

    # SHA-256 of content — skip scorer if unchanged
    content_hash: Mapped[str | None] = mapped_column(String(64))

    # Classification
    language: Mapped[str | None] = mapped_column(String(10), default="de")
    author: Mapped[str | None] = mapped_column(Text)
    category: Mapped[str | None] = mapped_column(Text)
    tags: Mapped[list | None] = mapped_column(JSONB, default=list)
    article_type: Mapped[str | None] = mapped_column(String(50), default="standard")
    connector_type: Mapped[str | None] = mapped_column(String(50), default="scraper")

    # Timestamps
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    modified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    scraped_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )

    # Raw scrape payload
    raw: Mapped[dict | None] = mapped_column(JSONB)

    # Tier-1 pre-screening (Mistral Small, title + first ~250 words)
    pre_score: Mapped[float | None] = mapped_column(Float)         # quick ragebait screen (0–10)
    pre_score_reasoning: Mapped[str | None] = mapped_column(Text)  # 1-sentence reasoning
    pre_score_model: Mapped[str | None] = mapped_column(String(100))
    pre_score_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Tier-2 full scoring (Mistral Large, full content)
    ragebait_score: Mapped[float | None] = mapped_column(Float)    # manufactured emotion (higher = worse)
    score_details: Mapped[dict | None] = mapped_column(JSONB)      # all sub-scores + reasoning
    score_model: Mapped[str | None] = mapped_column(String(100))
    score_version: Mapped[str | None] = mapped_column(String(20))
    score_computed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        UniqueConstraint(
            "source", "source_article_id",
            name="uix_articles_source_article_id",
        ),
        Index("ix_articles_url", "url"),
        Index("ix_articles_source_published", "source", "published_at"),
        Index("ix_articles_pre_score", "pre_score"),
        Index("ix_articles_ragebait_score", "ragebait_score"),
        Index("ix_articles_scraped_at", "scraped_at"),
    )
