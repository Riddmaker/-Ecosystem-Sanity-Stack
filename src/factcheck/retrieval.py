"""
Evidence retrieval for the Fact-Check track.

Two backends, used in order (winner-only design — see project plan):
  1. GoogleFactCheckClient — Google Fact Check Tools `claims:search`. FREE,
     returns *human-vetted* ClaimReview verdicts. First pass on the candidates.
  2. TavilyClient — Tavily web search for *novel* claims with no fact-check yet.
     Costs credits, so it runs only on the single judge-picked winner.

Both GUARD ON A MISSING KEY → return [] (and log at debug). The fact-check track
degrades gracefully and the ragebait track / local dev are never blocked: no
GOOGLE_FACTCHECK_API_KEY / TAVILY_API_KEY simply means no evidence from that
backend. HTTP via `requests` (already a dependency; same as the scrapers).

NOTE: Tavily's per-result `score` is a *relevance* score, not a credibility
score. Source reliability is judged downstream by the Mistral-Large scorer; here
we only shape *what* evidence comes back (news topic, recency, and excluding the
article's OWN domain so the evidence is independent of the outlet being checked).
"""

import logging
import os
from typing import Optional
from urllib.parse import urlparse

import requests

from src import config
from src.factcheck.schemas import FactCheckReview, WebEvidence
from src.scoring.throttle import google_fc_limiter, tavily_limiter

log = logging.getLogger(__name__)

GOOGLE_FC_URL = "https://factchecktools.googleapis.com/v1alpha1/claims:search"
TAVILY_URL    = "https://api.tavily.com/search"
HTTP_TIMEOUT  = 15   # seconds — matches the scraper connectors


def domain_of(url: str) -> str:
    """Bare registrable host of a URL ('https://www.20min.ch/x' → '20min.ch'). '' if unparyable."""
    try:
        host = urlparse(url).netloc.lower()
    except Exception:
        return ""
    return host[4:] if host.startswith("www.") else host


# ── Google Fact Check Tools (free, human-vetted) ─────────────────────

class GoogleFactCheckClient:
    """Look up whether a claim has ALREADY been fact-checked by a professional."""

    def __init__(self, api_key: Optional[str] = None):
        self._key = api_key or os.environ.get("GOOGLE_FACTCHECK_API_KEY")

    @property
    def available(self) -> bool:
        return bool(self._key)

    def search(
        self,
        query: str,
        language: Optional[str] = None,
        page_size: Optional[int] = None,
    ) -> list[FactCheckReview]:
        if not self._key:
            log.debug("GOOGLE_FACTCHECK_API_KEY not set — skipping fact-check lookup")
            return []
        if not (query or "").strip():
            return []

        google_fc_limiter.wait()
        params = {
            "query":        query,
            "key":          self._key,
            "languageCode": language or config.GOOGLE_FC_LANGUAGE,
            "pageSize":     page_size or config.GOOGLE_FC_PAGE_SIZE,
        }
        try:
            resp = requests.get(GOOGLE_FC_URL, params=params, timeout=HTTP_TIMEOUT)
            resp.raise_for_status()
            data = resp.json()
        except Exception:
            log.exception("Google Fact Check lookup failed: %s", query[:60])
            return []
        return _parse_fact_check(data)


def _parse_fact_check(data: dict) -> list[FactCheckReview]:
    reviews: list[FactCheckReview] = []
    for claim in (data.get("claims") or []):
        for r in (claim.get("claimReview") or []):
            pub = r.get("publisher") or {}
            reviews.append(FactCheckReview(
                publisher=pub.get("name", "") or "",
                site=pub.get("site", "") or "",
                url=r.get("url", "") or "",
                title=r.get("title", "") or "",
                rating=r.get("textualRating", "") or "",
                review_date=r.get("reviewDate", "") or "",
                language=r.get("languageCode", "") or "",
                claim_text=claim.get("text", "") or "",
                claimant=claim.get("claimant", "") or "",
            ))
    return reviews


# ── Tavily web search (credits — winner only) ────────────────────────

class TavilyClient:
    """Retrieve ranked, LLM-ready web evidence for a novel claim."""

    def __init__(self, api_key: Optional[str] = None):
        self._key = api_key or os.environ.get("TAVILY_API_KEY")

    @property
    def available(self) -> bool:
        return bool(self._key)

    def search(
        self,
        query: str,
        exclude_domains: Optional[list[str]] = None,
        max_results: Optional[int] = None,
        topic: Optional[str] = None,
        time_range: Optional[str] = None,
    ) -> list[WebEvidence]:
        if not self._key:
            log.debug("TAVILY_API_KEY not set — skipping web retrieval")
            return []
        if not (query or "").strip():
            return []

        tavily_limiter.wait()
        body: dict = {
            "query":        query,
            "search_depth": "basic",        # 1 credit (advanced = 2); volume is tiny
            "topic":        topic or config.TAVILY_TOPIC,
            "max_results":  max_results or config.TAVILY_MAX_RESULTS,
        }
        tr = time_range or config.TAVILY_TIME_RANGE
        if tr:
            body["time_range"] = tr
        if exclude_domains:
            body["exclude_domains"] = exclude_domains
        headers = {"Authorization": f"Bearer {self._key}"}
        try:
            resp = requests.post(TAVILY_URL, json=body, headers=headers, timeout=HTTP_TIMEOUT)
            resp.raise_for_status()
            data = resp.json()
        except Exception:
            log.exception("Tavily search failed: %s", query[:60])
            return []
        return [
            WebEvidence(
                title=r.get("title", "") or "",
                url=r.get("url", "") or "",
                content=r.get("content", "") or "",
                score=float(r.get("score") or 0.0),
            )
            for r in (data.get("results") or [])
        ]


# ── Per-claim evidence orchestration (winner only) ───────────────────

def gather_claim_evidence(
    claims: list[str],
    fct: GoogleFactCheckClient,
    tavily: TavilyClient,
    exclude_domains: Optional[list[str]] = None,
) -> list[dict]:
    """
    For each claim: Google Fact Check Tools first (free, human-vetted); fall back
    to Tavily web search ONLY when FCT returns nothing (credits — winner only).

    Returns a JSONB-ready list of per-claim bundles:
        [{"claim": str,
          "fact_checks": [FactCheckReview.model_dump(), ...],
          "web_evidence": [WebEvidence.model_dump(), ...]}]
    Both backends self-skip when their key is missing, so this degrades to
    empty evidence (→ the scorer abstains to NEI) rather than failing.
    """
    bundles: list[dict] = []
    for claim in claims:
        reviews = fct.search(claim)
        web: list[WebEvidence] = []
        if not reviews:
            web = tavily.search(claim, exclude_domains=exclude_domains)
            # Drop off-topic noise: Tavily returns a best-effort top-N even when
            # nothing in its index matches, so a hyperlocal claim can come back
            # with near-zero-relevance junk. Below the floor it isn't evidence —
            # an empty bundle makes the scorer abstain to NEI (the honest outcome).
            web = [w for w in web if w.score >= config.TAVILY_MIN_RELEVANCE]
        bundles.append({
            "claim":        claim,
            "fact_checks":  [r.model_dump() for r in reviews],
            "web_evidence": [w.model_dump() for w in web],
        })
    return bundles
