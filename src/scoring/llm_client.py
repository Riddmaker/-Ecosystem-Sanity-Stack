"""
Shared Mistral chat-completion client used by both scoring tiers.

Owns the plumbing that was previously duplicated in PreScorer and
MediaScorer: API-key handling, JSON response format, deterministic
sampling, rate limiting, and 429 retry with linear backoff.
"""

import json
import logging
import os
import time
from typing import Optional

from mistralai.client import Mistral
from mistralai.client.errors import SDKError

log = logging.getLogger(__name__)

# Deterministic sampling — recorded in score_details for reproducibility
TEMPERATURE = 0.0
RANDOM_SEED = 42


def _is_rate_limit(exc: Exception) -> bool:
    if isinstance(exc, SDKError):
        status = getattr(exc.raw_response, "status_code", None)
        if status is not None:
            return status == 429
    # Fallback for errors that don't carry a response object
    return "429" in str(exc)


class MistralJSONClient:
    """
    One model + one rate limiter; query_json() returns a parsed JSON dict.

    Usage:
        client = MistralJSONClient("mistral-small-latest", small_limiter)
        data = client.query_json(system_prompt, user_prompt)
    """

    def __init__(self, model: str, limiter, api_key: Optional[str] = None):
        key = api_key or os.environ.get("MISTRAL_API_KEY")
        if not key:
            raise ValueError("No API key provided. Set MISTRAL_API_KEY env variable.")
        self._client = Mistral(api_key=key)
        self.model = model
        self._limiter = limiter

    def query_json(self, system: str, user: str, retries: int = 4) -> dict:
        for attempt in range(retries):
            self._limiter.wait()
            try:
                response = self._client.chat.complete(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": system},
                        {"role": "user",   "content": user},
                    ],
                    response_format={"type": "json_object"},
                    temperature=TEMPERATURE,
                    random_seed=RANDOM_SEED,
                )
                raw = json.loads(response.choices[0].message.content)
                if isinstance(raw, list) and raw:
                    raw = raw[0]
                return raw
            except Exception as e:
                if _is_rate_limit(e) and attempt < retries - 1:
                    backoff = 10 * (attempt + 1)  # 10s, 20s, 30s
                    log.warning("%s rate limited — retrying in %ds", self.model, backoff)
                    time.sleep(backoff)
                else:
                    raise
        raise RuntimeError("query_json exhausted retries without raising")  # unreachable
