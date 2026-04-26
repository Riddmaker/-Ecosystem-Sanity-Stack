"""
ArticleRepository — persistence layer for scraped articles.

Dedup / match priority:
  1. source + source_article_id  (robust — works across connectors)
  2. url fallback                (for sources without extractable article IDs)

Upsert logic:
  - content_changed=True  → new or updated article → scorer should run
  - content_changed=False → identical content → only scraped_at updated
"""

import hashlib
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.connectors.abstract.models import Article
from src.db.models import ArticleModel


def _hash_content(title: str, content: str) -> str:
    return hashlib.sha256(f"{title}\n{content}".encode("utf-8")).hexdigest()


class ArticleRepository:

    def __init__(self, session: Session):
        self.session = session

    def _find_existing(self, article: Article) -> ArticleModel | None:
        """Look up an existing record — source+ID first, URL as fallback."""
        if article.source and article.source_article_id:
            existing = self.session.scalar(
                select(ArticleModel).where(
                    ArticleModel.source == article.source,
                    ArticleModel.source_article_id == article.source_article_id,
                )
            )
            if existing:
                return existing

        # Fallback: URL match
        return self.session.scalar(
            select(ArticleModel).where(ArticleModel.url == article.url)
        )

    def upsert(self, article: Article) -> tuple[ArticleModel, bool]:
        """
        Insert or update an article.

        Returns (model, content_changed):
          content_changed=True  → new or updated → scorer should run
          content_changed=False → identical content → skip scorer
        """
        now = datetime.now(timezone.utc)
        new_hash = _hash_content(article.title or "", article.content or "") if (article.title or article.content) else None
        existing = self._find_existing(article)

        if existing is None:
            model = ArticleModel(
                url=article.url,
                source=article.source,
                source_article_id=article.source_article_id,
                title=article.title,
                content=article.content,
                summary=article.summary,
                content_hash=new_hash,
                word_count=article.word_count,
                published_at=article.published_at,
                modified_at=article.published_at,
                scraped_at=now,
                language=article.language,
                author=article.author,
                category=article.category,
                tags=article.tags,
                article_type=article.article_type,
                connector_type=article.connector_type,
                raw=article.raw,
            )
            self.session.add(model)
            return model, True

        content_changed = existing.content_hash != new_hash

        # Always update scraped_at
        existing.scraped_at = now
        # Keep URL current (may have changed for liveblogs)
        existing.url = article.url

        if content_changed:
            existing.title = article.title
            existing.content = article.content
            existing.summary = article.summary
            existing.content_hash = new_hash
            existing.word_count = article.word_count
            existing.modified_at = now
            existing.author = article.author
            existing.category = article.category
            existing.tags = article.tags
            existing.raw = article.raw
            # Reset all scores — content changed, needs re-screening and re-scoring
            existing.pre_score = None
            existing.pre_score_model = None
            existing.pre_score_at = None
            existing.ragebait_score = None
            existing.score_details = None
            existing.score_model = None
            existing.score_version = None
            existing.score_computed_at = None

        return existing, content_changed

    def upsert_many(self, articles: list[Article]) -> dict[str, bool]:
        """Upsert a list of articles. Returns {url: content_changed} map."""
        return {a.url: self.upsert(a)[1] for a in articles}

    def get_unscored(self) -> list[ArticleModel]:
        """Return all articles that need a (re-)score."""
        return list(
            self.session.scalars(
                select(ArticleModel).where(
                    ArticleModel.ragebait_score.is_(None)
                )
            )
        )

    def get_unprescored(self, urls: list[str] | None = None) -> list[ArticleModel]:
        """Return articles that haven't been pre-scored yet, optionally filtered by URL list."""
        q = select(ArticleModel).where(ArticleModel.pre_score.is_(None))
        if urls:
            q = q.where(ArticleModel.url.in_(urls))
        return list(self.session.scalars(q))

    def get_top_prescored_unscored(self, n: int = 3) -> list[ArticleModel]:
        """Return top N articles by pre_score that haven't been fully scored yet."""
        from sqlalchemy import desc
        return list(self.session.scalars(
            select(ArticleModel)
            .where(
                ArticleModel.pre_score.isnot(None),
                ArticleModel.ragebait_score.is_(None),
            )
            .order_by(desc(ArticleModel.pre_score))
            .limit(n)
        ))
