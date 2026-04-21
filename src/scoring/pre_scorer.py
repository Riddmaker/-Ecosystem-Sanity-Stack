"""
PreScorer — Tier-1 screening with Mistral Small.

Fast and cheap: title + first 750 words → single pre_score (0–10).
Runs on ALL newly scraped articles.
Top-scoring articles then get the full Tier-2 analysis.
"""

import json
import os
import time
from datetime import datetime, timezone
from typing import Optional

from mistralai.client import Mistral

from src.scoring.schemas import PreScoreResult
from src.scoring.pre_prompts import PRE_SCREEN_SYSTEM, PRE_SCREEN_USER

PRE_SCORE_MODEL_ID       = "mistral-small-latest"
PRE_SCORE_VERSION        = "v5-pre"
PRE_SCORE_THRESHOLD      = 5.0   # pre_score >= this → "flagged"
MAX_SNIPPET_WORDS        = 250   # title + lead + ~2 paragraphs; structural signals peak here
MAX_REQUESTS_PER_SECOND  = 5
MIN_INTERVAL             = 1.0 / MAX_REQUESTS_PER_SECOND


class PreScorer:
    """
    Tier-1 screener. Runs on all new articles per scrape batch.

    Usage:
        pre = PreScorer()
        result = pre.score(title="...", content="...")
        # result.score: float 0–10
    """

    def __init__(self, api_key: Optional[str] = None):
        key = api_key or os.environ.get("MISTRAL_API_KEY")
        if not key:
            raise ValueError("No API key provided. Set MISTRAL_API_KEY env variable.")
        self.client = Mistral(api_key=key)
        self._last_request_time: float = 0.0

    def score(self, title: str, content: str) -> PreScoreResult:
        words = (content or "").split()
        snippet = " ".join(words[:MAX_SNIPPET_WORDS])
        user_msg = PRE_SCREEN_USER.format(title=title or "", snippet=snippet)
        self._throttle()
        response = self.client.chat.complete(
            model=PRE_SCORE_MODEL_ID,
            messages=[
                {"role": "system", "content": PRE_SCREEN_SYSTEM},
                {"role": "user",   "content": user_msg},
            ],
            response_format={"type": "json_object"},
            temperature=0.0,
            random_seed=42,
        )
        data = json.loads(response.choices[0].message.content)
        return PreScoreResult.model_validate(data)

    def _throttle(self) -> None:
        elapsed = time.monotonic() - self._last_request_time
        wait = MIN_INTERVAL - elapsed
        if wait > 0:
            time.sleep(wait)
        self._last_request_time = time.monotonic()


def pre_score_to_db_fields(result: PreScoreResult) -> dict:
    return {
        "pre_score":           result.score,
        "pre_score_reasoning": result.reasoning,
        "pre_score_model":     PRE_SCORE_MODEL_ID,
        "pre_score_at":        datetime.now(timezone.utc),
    }
