"""
Shared Mistral chat-completion client used by both scoring tiers.

Owns the plumbing that was previously duplicated in PreScorer and
MediaScorer: API-key handling, JSON response format, deterministic
sampling, rate limiting, and 429 retry that honours the server's
Retry-After header (with jittered exponential back-off as a fallback).
"""

import json
import logging
import os
import random
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


def _retry_after_seconds(exc: Exception, attempt: int) -> float:
    """
    How long to wait before retrying a 429. Prefer the server's Retry-After
    header (the only value that actually reflects the workspace budget — and the
    only thing that coordinates correctly when several processes share the same
    Mistral limit). Fall back to exponential back-off (5, 10, 20, 40s cap).
    """
    resp = getattr(exc, "raw_response", None)
    headers = getattr(resp, "headers", None)
    if headers is not None:
        try:
            ra = headers.get("retry-after") or headers.get("Retry-After")
        except AttributeError:
            ra = None
        if ra:
            try:
                return max(0.0, float(ra))
            except (TypeError, ValueError):
                pass  # non-numeric (HTTP-date) — fall through to back-off
    return min(40.0, 5.0 * (2 ** attempt))


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
                    # Jitter de-synchronises parallel sub-score threads so they
                    # don't all wake and re-fire into the limit at the same instant.
                    backoff = _retry_after_seconds(e, attempt) + random.uniform(0.0, 1.5)
                    log.warning("%s rate limited — retrying in %.1fs", self.model, backoff)
                    time.sleep(backoff)
                else:
                    raise
        raise RuntimeError("query_json exhausted retries without raising")  # unreachable
