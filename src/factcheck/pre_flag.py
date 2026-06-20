"""
FactCheckPreFlagger — Tier-1 fact-check pre-flag with Mistral Small.

Cheap check-worthiness triage: title + first ~250 words → one suspicion score
(0–10) that the article carries unverified / unsourced / contested claims worth
a grounded fact-check. Runs on all new/changed articles when the fact-check
track is enabled; the most-suspicious then get the Tier-2 verdict.

Screens *check-worthiness* (Hassan et al. 2017), not truth — the grounded
verdict (and any abstain/NEI) happens in Tier-2. Mirrors
src/scoring/pre_scorer.py::PreScorer.
"""

from datetime import datetime, timezone
from typing import Optional

from src.scoring.llm_client import MistralJSONClient
from src.scoring.throttle import small_limiter
from src.factcheck.schemas import FcPreFlagResult
from src.factcheck.prompts import PRE_FLAG_SYSTEM, PRE_FLAG_USER

# Same cheap, high-RPS Small snapshot the ragebait pre-screen uses (see
# pre_scorer.PRE_SCORE_MODEL_ID). Kept as its own constant so the two tracks
# can diverge; the plan is to later fold both into one Small call per article.
FC_PRE_FLAG_MODEL_ID = "mistral-small-2506"
MAX_SNIPPET_WORDS    = 250   # title + lead + ~2 paragraphs


class FactCheckPreFlagger:
    """
    Tier-1 fact-check screener. Runs on all new articles per scrape batch
    when config.FACTCHECK_ENABLED is set.

    Usage:
        flagger = FactCheckPreFlagger()
        result = flagger.flag(title="...", content="...")
        # result.score: float 0–10 (higher = more worth checking)
    """

    def __init__(self, api_key: Optional[str] = None):
        self._client = MistralJSONClient(FC_PRE_FLAG_MODEL_ID, small_limiter, api_key)

    def flag(self, title: str, content: str) -> FcPreFlagResult:
        words = (content or "").split()
        snippet = " ".join(words[:MAX_SNIPPET_WORDS])
        user_msg = PRE_FLAG_USER.format(title=title or "", snippet=snippet)
        data = self._client.query_json(PRE_FLAG_SYSTEM, user_msg)
        return FcPreFlagResult.model_validate(data)


def fc_pre_flag_to_db_fields(result: FcPreFlagResult) -> dict:
    return {
        "fc_pre_score":     result.score,
        "fc_pre_reasoning": result.reasoning,
        "fc_pre_model":     FC_PRE_FLAG_MODEL_ID,
        "fc_pre_at":        datetime.now(timezone.utc),
    }
