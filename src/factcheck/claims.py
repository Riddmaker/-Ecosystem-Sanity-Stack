"""
ClaimExtractor — pull checkable factual claims out of an article (Mistral Small).

SAFE (Wei et al. 2024) / Claimify (Microsoft 2025) style: decompose an article
into atomic, self-contained, *checkable* claims so each can be sent to evidence
retrieval (Google Fact Check Tools → Tavily) on its own. Cheap Small-tier call;
in the winner-only design only the judge-picked article is decomposed.
"""

import logging
from typing import Optional

from src import config
from src.scoring.llm_client import MistralJSONClient
from src.scoring.throttle import small_limiter
from src.factcheck.schemas import ClaimExtraction
from src.factcheck.prompts import CLAIM_EXTRACT_SYSTEM, CLAIM_EXTRACT_USER

log = logging.getLogger(__name__)

# Reuse the cheap, high-RPS Small snapshot (see pre_flag.FC_PRE_FLAG_MODEL_ID).
CLAIM_MODEL_ID  = "mistral-small-2506"
# Bound the prompt: claims worth checking cluster in the body, not the tail.
CLAIM_MAX_WORDS = 1200


class ClaimExtractor:
    """
    Usage:
        ex = ClaimExtractor()
        claims = ex.extract(title="...", content="...")   # list[str], <= max_claims
    """

    def __init__(self, api_key: Optional[str] = None):
        self._client = MistralJSONClient(CLAIM_MODEL_ID, small_limiter, api_key)

    def extract(self, title: str, content: str, max_claims: Optional[int] = None) -> list[str]:
        cap = max_claims if max_claims is not None else config.FACTCHECK_MAX_CLAIMS
        words = (content or "").split()
        body = " ".join(words[:CLAIM_MAX_WORDS])
        system = CLAIM_EXTRACT_SYSTEM.format(max_claims=cap)
        user = CLAIM_EXTRACT_USER.format(title=title or "", content=body)
        data = self._client.query_json(system, user)
        result = ClaimExtraction.model_validate(data)
        # Drop blanks and trim to the cap (the model can overshoot).
        claims = [c.strip() for c in result.claims if c and c.strip()]
        return claims[:cap]
