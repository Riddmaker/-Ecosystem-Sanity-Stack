"""
Test the MediaScorer against a single article from the DB.
Usage: .venv/Scripts/python test_scorer.py
"""

from dotenv import load_dotenv
load_dotenv()

from sqlalchemy import select
from src.db.connection import build_engine, get_session
from src.db.models import ArticleModel
from src.scoring.scorer import MediaScorer, result_to_db_fields

engine = build_engine()

with get_session() as session:
    # Grab one article that hasn't been scored yet
    article = session.scalar(
        select(ArticleModel).where(ArticleModel.ragebait_score.is_(None)).limit(1)
    )

    if not article:
        print("No unscored articles found. Run test_scraper.py first.")
        exit()

    print(f"Scoring: {article.title}\n")

    scorer = MediaScorer()
    result = scorer.score(title=article.title, content=article.content)

    # Persist
    fields = result_to_db_fields(result)
    for key, val in fields.items():
        setattr(article, key, val)

print(f"\n{'='*60}")
print(f"RAGEBAIT INDEX:    {result.ragebait_score} / 10  (higher = more manufactured)")
print(f"EMOTIONAL WEIGHT:  {result.emotional_weight} / 10  (neutral descriptor)")
print(f"\nRagebait sub-scores:")
print(f"  curiosity_gap:       {result.ragebait.curiosity_gap}")
print(f"  conflict_staging:    {result.ragebait.conflict_staging}")
print(f"  emotional_inflation: {result.ragebait.emotional_inflation}")
print(f"  reasoning: {result.ragebait.reasoning}")
print(f"\nEmotional Weight sub-scores:")
print(f"  topic_gravity:       {result.emotional_weight_detail.topic_gravity}")
print(f"  emotional_exposure:  {result.emotional_weight_detail.emotional_exposure}")
print(f"  reader_burden:       {result.emotional_weight_detail.reader_burden}")
print(f"  reasoning: {result.emotional_weight_detail.reasoning}")
