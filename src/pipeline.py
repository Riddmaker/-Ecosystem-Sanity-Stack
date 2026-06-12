"""
Core pipeline logic — importable function so it can be called from both
the CLI (run_pipeline.py) and the scheduler (scheduler.py).
"""

import sys
from datetime import datetime, timezone, timedelta
from typing import Optional

from src.db.connection import build_engine, create_tables, get_session
from src.db.repository import ArticleRepository
from src.connectors.specific_scraper.twenty_minutes_scraper_connector import (
    TwentyMinutesScraperConnector,
    DEFAULT_SECTIONS as TWENTYMIN_SECTIONS,
)
from src.connectors.specific_scraper.watson_scraper_connector import (
    WatsonScraperConnector,
    DEFAULT_SECTIONS as WATSON_SECTIONS,
)
from src.connectors.specific_scraper.blick_scraper_connector import (
    BlickScraperConnector,
    DEFAULT_SECTIONS as BLICK_SECTIONS,
)
from src.connectors.specific_scraper.nau_scraper_connector import (
    NauScraperConnector,
    DEFAULT_SECTIONS as NAU_SECTIONS,
)
from src.scoring.pre_scorer import PreScorer, pre_score_to_db_fields
from src.scoring.scorer import MediaScorer, result_to_db_fields

ALL_SOURCES = ["20min", "watson", "blick", "nau"]


def run(
    hours: Optional[float] = None,
    max_articles: Optional[int] = None,
    sources: Optional[list[str]] = None,
) -> bool:
    """
    Run the full pipeline: scrape → upsert → pre-screen → full-score top 3.

    Args:
        hours:        Only include articles published within the last N hours.
        max_articles: Hard cap on articles fetched per source.
        sources:      Which sources to scrape. Defaults to all three.

    Returns:
        True if at least one article was fully scored, False otherwise.
    """
    if sources is None:
        sources = ALL_SOURCES

    build_engine()
    create_tables(build_engine())

    now = datetime.now(timezone.utc)
    since = now - timedelta(hours=hours) if hours else None

    print(f"\n[pipeline] {now.strftime('%Y-%m-%d %H:%M UTC')}")
    if since:
        print(f"[pipeline] Filter: articles since {since.strftime('%H:%M UTC')} (--hours {hours})")
    if max_articles:
        print(f"[pipeline] Cap: max {max_articles} articles per source")
    print(f"[pipeline] Sources: {', '.join(sources)}")
    print("=" * 60)

    # ── 1. Scrape ────────────────────────────────────────────────
    print("\n[1/4] Scraping sources...")
    all_articles = []

    if "20min" in sources:
        print("      20min.ch")
        try:
            fetched = TwentyMinutesScraperConnector(sections=TWENTYMIN_SECTIONS).get_articles(
                since=since, max_articles=max_articles
            )
            all_articles.extend(fetched)
            print(f"      → {len(fetched)} articles")
        except Exception as e:
            print(f"      ERROR: {e}")

    if "watson" in sources:
        print("      watson.ch")
        try:
            fetched = WatsonScraperConnector(sections=WATSON_SECTIONS).get_articles(
                since=since, max_articles=max_articles
            )
            all_articles.extend(fetched)
            print(f"      → {len(fetched)} articles")
        except Exception as e:
            print(f"      ERROR: {e}")

    if "blick" in sources:
        print("      blick.ch")
        try:
            fetched = BlickScraperConnector(sections=BLICK_SECTIONS).get_articles(
                since=since, max_articles=max_articles
            )
            all_articles.extend(fetched)
            print(f"      → {len(fetched)} articles")
        except Exception as e:
            print(f"      ERROR: {e}")

    if "nau" in sources:
        print("      nau.ch")
        try:
            fetched = NauScraperConnector(sections=NAU_SECTIONS).get_articles(
                since=since, max_articles=max_articles
            )
            all_articles.extend(fetched)
            print(f"      → {len(fetched)} articles")
        except Exception as e:
            print(f"      ERROR: {e}")

    print(f"      Total: {len(all_articles)} articles across all sources")

    # ── 2. Upsert ────────────────────────────────────────────────
    print("\n[2/4] Upserting to DB...")
    with get_session() as session:
        repo = ArticleRepository(session)
        results = repo.upsert_many(all_articles)

    new_or_updated_urls = [url for url, changed in results.items() if changed]
    unchanged_urls      = [url for url, changed in results.items() if not changed]
    print(f"      {len(new_or_updated_urls)} new/updated   {len(unchanged_urls)} unchanged")

    # ── 3. Pre-screen ────────────────────────────────────────────
    print(f"\n[3/4] Pre-screening {len(new_or_updated_urls)} articles with Mistral Small...")

    if not new_or_updated_urls:
        print("      Nothing to pre-score.")
    else:
        pre_scorer = PreScorer()
        with get_session() as session:
            repo = ArticleRepository(session)
            to_prescreen = repo.get_unprescored(urls=new_or_updated_urls)

            for article in to_prescreen:
                # Skip paywalled / teaser-only articles — scoring truncated marketing
                # copy inflates every dimension artificially and causes hallucinations.
                # Blick marks paid content with "(B+)" in the title; the word-count
                # guard catches teasers from any source.
                word_count = article.word_count or len((article.content or "").split())
                is_paywalled = (
                    "(B+)" in (article.title or "")
                    or "(b+)" in (article.title or "").lower()
                    or word_count < 100
                )
                if is_paywalled:
                    # Mark as screened so it doesn't requeue every run
                    article.pre_score         = 0.0
                    article.pre_score_reasoning = "SKIP: paywalled or teaser-only content"
                    article.pre_score_model   = "none"
                    article.pre_score_at      = datetime.now(timezone.utc)
                    session.flush()
                    print(f"      [paywall] {article.title[:60]}")
                    continue

                try:
                    result = pre_scorer.score(
                        title=article.title or "", content=article.content or ""
                    )
                    fields = pre_score_to_db_fields(result)
                    for k, v in fields.items():
                        setattr(article, k, v)
                    session.flush()

                    print(f"      {result.score:.1f}  {article.title[:60]}")
                except Exception as e:
                    print(f"      [ERR] {article.title[:60]}: {e}")

    # ── 4. Gate → full-score → judge ─────────────────────────────
    print("\n[4/4] Qualitative gate + full-scoring with Mistral Large...")

    fully_scored = False
    with get_session() as session:
        repo = ArticleRepository(session)
        gate_candidates = repo.get_prescored_above_threshold(min_score=3.0, limit=12)

        if not gate_candidates:
            print("      No candidates above pre-score threshold.")
        else:
            scorer = MediaScorer()

            # ── Gate: filter for genuine editorial inflation ──────
            print(f"      Running qualitative gate on {len(gate_candidates)} candidates...")
            candidates = []
            for gc in gate_candidates:
                try:
                    gate = scorer.gate_article(
                        title=gc.title or "", content=gc.content or ""
                    )
                    verdict = "PASS" if gate["pass"] else "SKIP"
                    print(f"      [{verdict}] pre={gc.pre_score:.1f}  \"{gc.title[:55]}\"")
                    print(f"             {gate['reasoning'][:100]}")
                    if gate["pass"]:
                        candidates.append(gc)
                except Exception as e:
                    print(f"      [GATE ERR] {gc.title[:55]}: {e}")
                    candidates.append(gc)  # on gate error, include to be safe

            if not candidates:
                print("      Gate filtered all candidates — no genuine editorial inflation detected today.")
            else:
                print(f"      {len(candidates)} article(s) passed the gate.")

            scored = []
            for candidate in candidates:
                print(f"      → Scoring: \"{candidate.title[:60]}\"")
                try:
                    result = scorer.score(
                        title=candidate.title or "", content=candidate.content or ""
                    )
                    fields = result_to_db_fields(result)
                    for k, v in fields.items():
                        setattr(candidate, k, v)
                    session.flush()
                    print(f"         ragebait={result.ragebait_score:.1f}")
                    scored.append((candidate, result))
                    fully_scored = True
                except Exception as e:
                    print(f"         ERROR: {e}")

            if len(scored) > 1:
                # ── Judge: qualitative winner selection ──────────────
                print(f"\n      Asking judge to pick winner from {len(scored)} candidates...")
                judge_input = [
                    {
                        "title":                  c.title or "",
                        "ragebait_score":         r.ragebait_score,
                        "curiosity_gap":          r.ragebait.curiosity_gap,
                        "conflict_staging":       r.ragebait.conflict_staging,
                        "emotional_inflation":    r.ragebait.emotional_inflation,
                        "narrative_exploitation": r.ragebait.narrative_exploitation,
                        "reasoning":              r.ragebait.reasoning,
                    }
                    for c, r in scored
                ]
                try:
                    judge_result = scorer.judge_articles(judge_input)
                    idx = judge_result["chosen"] - 1  # 0-indexed
                    winner_article, winner_result = scored[idx]
                    judge_reasoning = judge_result["reasoning"]
                    print(f"      Judge chose Artikel {judge_result['chosen']}: \"{winner_article.title[:70]}\"")
                    print(f"      Reasoning: {judge_reasoning}")

                    # Write judge result into winner's score_details
                    if winner_article.score_details:
                        winner_article.score_details = {
                            **winner_article.score_details,
                            "judge": {
                                "selected":  True,
                                "reasoning": judge_reasoning,
                            },
                        }
                        session.flush()

                    # Reader service: factual extract for every judge-picked article
                    # Skip if content is too thin (paywalled teaser) — hallucination risk
                    content_words = len((winner_article.content or "").split())
                    if content_words < 80:
                        print(f"      Skipping reader service — content too short ({content_words} words, likely paywalled teaser)")
                    elif True:
                        try:
                            print(f"      Generating reader service (ragebait={winner_result.ragebait_score:.1f})...")
                            reader_service = scorer.generate_reader_service(
                                title=winner_article.title or "",
                                content=winner_article.content or "",
                                score_result=winner_result,
                            )
                            winner_article.score_details = {
                                **winner_article.score_details,
                                "reader_service": reader_service,
                            }
                            session.flush()
                        except Exception as e:
                            print(f"      Reader service ERROR: {e}")
                except Exception as e:
                    print(f"      Judge ERROR: {e} — falling back to highest ragebait_score")
                    idx = max(range(len(scored)), key=lambda i: scored[i][1].ragebait_score)
                    winner_article, winner_result = scored[idx]

                print(f"\n      Dashboard highlight: \"{winner_article.title[:70]}\"")
                print(f"      ragebait={winner_result.ragebait_score:.1f}")

            elif scored:
                winner_article, winner_result = scored[0]
                print(f"\n      Dashboard highlight (single candidate): \"{winner_article.title[:70]}\"")
                print(f"      ragebait={winner_result.ragebait_score:.1f}")

    print("\n[pipeline] Done.")
    print("=" * 60)
    return fully_scored
