"""
Model comparison: mistral-large-latest
Scores all articles currently in the DB and saves results to model_comparison.json
No scraping — uses existing DB data only.
"""

import json
from datetime import datetime, timezone
from dotenv import load_dotenv
load_dotenv()

from sqlalchemy import select
from src.db.connection import build_engine, get_session
from src.db.models import ArticleModel
from src.scoring.scorer import SanityScorer

MODELS = [
    "mistral-large-latest",
]

engine = build_engine()

# Load all articles from DB
with get_session() as session:
    articles = list(session.scalars(select(ArticleModel)))

if not articles:
    print("No articles in DB. Run test_scraper.py first.")
    exit()

print(f"Found {len(articles)} articles in DB.\n")

results = []

for article in articles:
    print(f"\n{'='*60}")
    print(f"ARTIKEL: {article.title[:70]}")
    print(f"Woerter: {article.word_count} | Kategorie: {article.category}")

    article_result = {
        "id":         str(article.id),
        "title":      article.title,
        "url":        article.url,
        "author":     article.author,
        "category":   article.category,
        "word_count": article.word_count,
        "scores":     {},
    }

    for model_id in MODELS:
        print(f"\n  >> Scoring mit {model_id}...")
        try:
            scorer = SanityScorer(model=model_id)
            result = scorer.score(title=article.title, content=article.content or "")

            article_result["scores"][model_id] = {
                "sanity_score": result.sanity_score,
                "dimensions": {
                    "consumption_pull": {
                        "score":                result.consumption_pull.score,
                        "urgency_framing":      result.consumption_pull.urgency_framing,
                        "unresolved_threat":    result.consumption_pull.unresolved_threat,
                        "cliffhanger_structure":result.consumption_pull.cliffhanger_structure,
                        "reasoning":            result.consumption_pull.reasoning,
                    },
                    "reality_distortion": {
                        "score":            result.reality_distortion.score,
                        "negativity_ratio": result.reality_distortion.negativity_ratio,
                        "context_absence":  result.reality_distortion.context_absence,
                        "agency_vacuum":    result.reality_distortion.agency_vacuum,
                        "reasoning":        result.reality_distortion.reasoning,
                    },
                    "outrage_drain": {
                        "score":             result.outrage_drain.score,
                        "stakes_inflation":  result.outrage_drain.stakes_inflation,
                        "actionability_gap": result.outrage_drain.actionability_gap,
                        "moral_grandiosity": result.outrage_drain.moral_grandiosity,
                        "reasoning":         result.outrage_drain.reasoning,
                    },
                },
            }
            print(f"     Sanity Score: {result.sanity_score}")
            print(f"     Consumption Pull:   {result.consumption_pull.score}")
            print(f"     Reality Distortion: {result.reality_distortion.score}")
            print(f"     Outrage Drain:      {result.outrage_drain.score}")

        except Exception as e:
            print(f"     FEHLER: {e}")
            article_result["scores"][model_id] = {"error": str(e)}

    results.append(article_result)

# Summary
output = {
    "generated_at":  datetime.now(timezone.utc).isoformat(),
    "models":        MODELS,
    "article_count": len(results),
    "articles":      results,
}

# Sort by sanity score descending
output["articles"].sort(
    key=lambda a: a["scores"].get("mistral-large-latest", {}).get("sanity_score", 0),
    reverse=True,
)

with open("model_comparison.json", "w", encoding="utf-8") as f:
    json.dump(output, f, ensure_ascii=False, indent=2)

print(f"\n{'='*60}")
print(f"Gespeichert: model_comparison.json")
print(f"\nRanking nach Sanity Score:")
for a in output["articles"]:
    score = a["scores"].get("mistral-large-latest", {}).get("sanity_score", "?")
    title = a["title"][:60] if a["title"] else "?"
    print(f"  {score:>4}  {title}")
