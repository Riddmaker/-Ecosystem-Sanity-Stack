"""
Migration v3 → v4

Changes:
  - Rename column: sanity_score      → ragebait_score
  - Rename column: civic_utility_score → emotional_weight
  - Drop old indexes, create new indexes
  - Reset all scores (force re-score with new prompts)
  - Re-score all articles

Run with:
  .venv/Scripts/python migrate_v3_to_v4.py
"""

from dotenv import load_dotenv
load_dotenv()

from sqlalchemy import text
from src.db.connection import build_engine, get_session
from src.db.models import ArticleModel
from src.scoring.scorer import MediaScorer, result_to_db_fields
from sqlalchemy import select

engine = build_engine()

# ── 1. Schema: ensure indexes exist (columns already renamed in prior migration) ──
print("Step 1: Ensuring indexes...")
with engine.connect() as conn:
    conn.execute(text("DROP INDEX IF EXISTS ix_articles_sanity_score;"))
    conn.execute(text("DROP INDEX IF EXISTS ix_articles_civic_utility_score;"))
    conn.execute(text(
        "CREATE INDEX IF NOT EXISTS ix_articles_ragebait_score ON articles (ragebait_score);"
    ))
    conn.execute(text(
        "CREATE INDEX IF NOT EXISTS ix_articles_emotional_weight ON articles (emotional_weight);"
    ))
    conn.commit()
print("  OK: Indexes updated")


# ── 2. Reset all scores ──────────────────────────────────────────────────────
print("Step 2: Resetting all scores...")
with engine.connect() as conn:
    conn.execute(text("""
        UPDATE articles SET
            ragebait_score    = NULL,
            emotional_weight  = NULL,
            score_details     = NULL,
            score_model       = NULL,
            score_version     = NULL,
            score_computed_at = NULL
    """))
    conn.commit()
print("  OK: All scores reset")


# ── 3. Re-score all articles ─────────────────────────────────────────────────
print("Step 3: Re-scoring all articles with v4 prompts...")
scorer = MediaScorer()

with get_session() as session:
    articles = list(session.scalars(select(ArticleModel)))
    total = len(articles)
    print(f"  Found {total} articles to score")

    for i, article in enumerate(articles, 1):
        print(f"  [{i}/{total}] {article.title[:70]}")
        try:
            result = scorer.score(title=article.title or "", content=article.content or "")
            fields = result_to_db_fields(result)
            for key, val in fields.items():
                setattr(article, key, val)
            session.flush()
            print(f"         ragebait={result.ragebait_score:.1f}  weight={result.emotional_weight:.1f}")
        except Exception as e:
            print(f"         ERROR: {e}")

print("\nMigration complete.")
