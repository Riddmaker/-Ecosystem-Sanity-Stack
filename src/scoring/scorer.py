"""
MediaScorer — runs 2 dimension queries against the Mistral API
and returns a ScoreResult with Ragebait Index + Emotional Weight.

Ragebait Index  — Is this emotion manufactured or authentic?
                  Blom & Hansen (2015), Potthast et al. (2016), Rony et al. (2017)
                  Higher = more manufactured. 0 = fully authentic, 10 = pure engagement farming.

Emotional Weight — How heavy is this content to process?
                   Neutral descriptor. No value judgment.
                   Context for interpreting the Ragebait Index.
"""

import json
import os
import time
from datetime import datetime, timezone
from typing import Optional

from mistralai.client import Mistral

from src.scoring.schemas import (
    RagebaitScore,
    EmotionalWeightScore,
    ScoreResult,
)
from src.scoring.prompts import (
    RAGEBAIT_SYSTEM, RAGEBAIT_USER,
    EMOTIONAL_WEIGHT_SYSTEM, EMOTIONAL_WEIGHT_USER,
)

SCORE_MODEL_ID   = "mistral-large-latest"
SCORE_VERSION    = "v4"
RANDOM_SEED      = 42
TEMPERATURE      = 0.0
MAX_REQUESTS_PER_SECOND = 5
MIN_INTERVAL     = 1.0 / MAX_REQUESTS_PER_SECOND
MAX_CONTENT_CHARS = 3000


class MediaScorer:
    """
    Scores a news article on 2 dimensions:
      - Ragebait Index    (higher = more manufactured emotion)
      - Emotional Weight  (neutral: how heavy to process)

    Usage:
        scorer = MediaScorer()
        result = scorer.score(title="...", content="...")
    """

    def __init__(self, api_key: Optional[str] = None, model: str = SCORE_MODEL_ID):
        key = api_key or os.environ.get("MISTRAL_API_KEY")
        if not key:
            raise ValueError("No API key provided. Set MISTRAL_API_KEY env variable.")
        self.client = Mistral(api_key=key)
        self.model  = model
        self._last_request_time: float = 0.0

    def score(self, title: str, content: str) -> ScoreResult:
        """Run both dimension queries and return aggregated ScoreResult."""
        content_trunc = content[:MAX_CONTENT_CHARS]

        ragebait        = self._score_ragebait(title, content_trunc)
        emotional_weight = self._score_emotional_weight(title, content_trunc)

        reasoning = " | ".join([
            f"[ragebait] {ragebait.reasoning}",
            f"[emotional_weight] {emotional_weight.reasoning}",
        ])

        return ScoreResult(
            ragebait_score=ragebait.score,
            emotional_weight=emotional_weight.score,
            ragebait=ragebait,
            emotional_weight_detail=emotional_weight,
            reasoning=reasoning,
        )

    # ------------------------------------------------------------------
    # Dimension queries
    # ------------------------------------------------------------------

    def _score_ragebait(self, title: str, content: str) -> RagebaitScore:
        return RagebaitScore.model_validate(
            self._query(RAGEBAIT_SYSTEM, RAGEBAIT_USER.format(title=title, content=content))
        )

    def _score_emotional_weight(self, title: str, content: str) -> EmotionalWeightScore:
        return EmotionalWeightScore.model_validate(
            self._query(EMOTIONAL_WEIGHT_SYSTEM, EMOTIONAL_WEIGHT_USER.format(title=title, content=content))
        )

    # ------------------------------------------------------------------
    # Mistral API call
    # ------------------------------------------------------------------

    def _throttle(self) -> None:
        elapsed = time.monotonic() - self._last_request_time
        wait = MIN_INTERVAL - elapsed
        if wait > 0:
            time.sleep(wait)
        self._last_request_time = time.monotonic()

    def _query(self, system: str, user: str) -> dict:
        self._throttle()
        response = self.client.chat.complete(
            model=self.model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user",   "content": user},
            ],
            response_format={"type": "json_object"},
            temperature=TEMPERATURE,
            random_seed=RANDOM_SEED,
        )
        return json.loads(response.choices[0].message.content)


def result_to_db_fields(result: ScoreResult) -> dict:
    """Convert a ScoreResult into fields for ArticleModel."""
    rb = result.ragebait
    ew = result.emotional_weight_detail
    return {
        "ragebait_score":  result.ragebait_score,
        "emotional_weight": result.emotional_weight,
        "score_details": {
            "ragebait_score":    result.ragebait_score,
            "emotional_weight_score": result.emotional_weight,
            "ragebait": {
                "score":               rb.score,
                "curiosity_gap":       rb.curiosity_gap,
                "conflict_staging":    rb.conflict_staging,
                "emotional_inflation": rb.emotional_inflation,
                "reasoning":           rb.reasoning,
            },
            "emotional_weight": {
                "score":              ew.score,
                "topic_gravity":      ew.topic_gravity,
                "emotional_exposure": ew.emotional_exposure,
                "reader_burden":      ew.reader_burden,
                "reasoning":          ew.reasoning,
            },
            "temperature": TEMPERATURE,
            "random_seed": RANDOM_SEED,
        },
        "score_model":       SCORE_MODEL_ID,
        "score_version":     SCORE_VERSION,
        "score_computed_at": datetime.now(timezone.utc),
    }
