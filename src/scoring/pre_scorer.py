"""
PreScorer — Tier-1 screening with Mistral Small.

Fast and cheap: title + first ~250 words → single pre_score (0–10).
Runs on ALL newly scraped articles.
Top-scoring articles then get the full Tier-2 analysis.
"""

from datetime import datetime, timezone
from typing import Optional

from src.scoring.llm_client import MistralJSONClient
from src.scoring.schemas import PreScoreResult
from src.scoring.pre_prompts import PRE_SCREEN_SYSTEM, PRE_SCREEN_USER
from src.scoring.throttle import small_limiter

# Pin the older Small snapshot (June 2025) rather than the floating -latest
# (which tracks the newer, pricier 2603 with a far lower RPS/TPM ceiling).
# 2506 is cheaper for cheap Tier-1 screening and has much higher rate limits
# (20 RPS / 5M TPM vs 1.67 RPS / 100k TPM). See admin.mistral.ai/plateforme/limits.
PRE_SCORE_MODEL_ID = "mistral-small-2506"
MAX_SNIPPET_WORDS  = 250   # title + lead + ~2 paragraphs; structural signals peak here


class PreScorer:
    """
    Tier-1 screener. Runs on all new articles per scrape batch.

    Usage:
        pre = PreScorer()
        result = pre.score(title="...", content="...")
        # result.score: float 0–10
    """

    def __init__(self, api_key: Optional[str] = None):
        self._client = MistralJSONClient(PRE_SCORE_MODEL_ID, small_limiter, api_key)

    def score(self, title: str, content: str) -> PreScoreResult:
        words = (content or "").split()
        snippet = " ".join(words[:MAX_SNIPPET_WORDS])
        user_msg = PRE_SCREEN_USER.format(title=title or "", snippet=snippet)
        data = self._client.query_json(PRE_SCREEN_SYSTEM, user_msg)
        return PreScoreResult.model_validate(data)


def pre_score_to_db_fields(result: PreScoreResult) -> dict:
    return {
        "pre_score":           result.score,
        "pre_score_reasoning": result.reasoning,
        "pre_score_model":     PRE_SCORE_MODEL_ID,
        "pre_score_at":        datetime.now(timezone.utc),
    }
