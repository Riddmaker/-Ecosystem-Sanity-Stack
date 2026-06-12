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
from src.scoring.throttle import small_limiter

PRE_SCORE_MODEL_ID = "mistral-small-latest"
PRE_SCORE_VERSION  = "v6-pre"
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
        key = api_key or os.environ.get("MISTRAL_API_KEY")
        if not key:
            raise ValueError("No API key provided. Set MISTRAL_API_KEY env variable.")
        self.client = Mistral(api_key=key)

    def score(self, title: str, content: str, _retries: int = 4) -> PreScoreResult:
        words = (content or "").split()
        snippet = " ".join(words[:MAX_SNIPPET_WORDS])
        user_msg = PRE_SCREEN_USER.format(title=title or "", snippet=snippet)
        for attempt in range(_retries):
            small_limiter.wait()
            try:
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
            except Exception as e:
                if "429" in str(e) and attempt < _retries - 1:
                    backoff = 10 * (attempt + 1)
                    time.sleep(backoff)
                else:
                    raise

def pre_score_to_db_fields(result: PreScoreResult) -> dict:
    return {
        "pre_score":           result.score,
        "pre_score_reasoning": result.reasoning,
        "pre_score_model":     PRE_SCORE_MODEL_ID,
        "pre_score_at":        datetime.now(timezone.utc),
    }
