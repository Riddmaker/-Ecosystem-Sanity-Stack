"""
Pydantic schemas for the Fact-Check track (Irreführungs-Index).

Tier-1 pre-flag — suspicion that an article carries checkable claims that are
unverified / unsourced / contested and therefore worth fact-checking. Higher =
more suspicious. This is check-worthiness triage (Hassan et al. 2017,
ClaimBuster), NOT a truth verdict — the grounded verdict happens in Tier-2 and
may abstain (NEI). Mirrors src/scoring/schemas.py::PreScoreResult.
"""

from pydantic import BaseModel, Field, model_validator


class FcPreFlagResult(BaseModel):
    """
    Tier-1 fact-check pre-flag — Mistral Small, title + first ~250 words.
    Single score: likelihood the article carries unverified/unchecked claims
    worth a grounded fact-check.
    """
    score: float = Field(ge=0, le=10)
    reasoning: str

    @model_validator(mode="before")
    @classmethod
    def normalise_reasoning_field(cls, data: dict) -> dict:
        """Accept 'reason' as an alias for 'reasoning' (model sometimes uses the wrong key)."""
        if isinstance(data, dict) and "reasoning" not in data and "reason" in data:
            data["reasoning"] = data.pop("reason")
        return data


class ClaimExtraction(BaseModel):
    """Output of claim extraction (Mistral Small) — checkable claims pulled from an article."""
    claims: list[str] = Field(default_factory=list)


class FactCheckReview(BaseModel):
    """
    One human fact-checker verdict from the Google Fact Check Tools API
    (a ClaimReview). Already vetted by a professional fact-checker — the
    strongest evidence we retrieve. JSONB-serialisable for fact_check_details.
    """
    publisher: str = ""        # claimReview.publisher.name
    site: str = ""             # claimReview.publisher.site
    url: str = ""              # link to the published fact-check
    title: str = ""
    rating: str = ""           # claimReview.textualRating, e.g. "Falsch"
    review_date: str = ""      # claimReview.reviewDate (ISO string)
    language: str = ""         # claimReview.languageCode
    claim_text: str = ""       # the claim the fact-check matched
    claimant: str = ""         # who originally made the claim


class WebEvidence(BaseModel):
    """One ranked web result from Tavily. JSONB-serialisable for fact_check_details."""
    title: str = ""
    url: str = ""
    content: str = ""          # clean snippet Tavily extracted
    score: float = 0.0         # Tavily relevance score (NOT a credibility score)
