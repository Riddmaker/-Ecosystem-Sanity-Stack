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


class FactCheckScore(BaseModel):
    """
    Grounded Tier-2 verdict — mean of three Mistral-Large sub-scores.
    Higher = more misleading (the Irreführungs-Index).

      - factual_accuracy   open-book, FEVER SUPPORTED/REFUTED/NEI (Thorne 2018)
      - misleading_framing closed-book, Entman (1993)
      - missing_context    closed-book, Rogers et al. (2017) — paltering

    Factual Accuracy ABSTAINS to NEI when evidence is thin; it is then excluded
    from the mean (accuracy_counted=False) so abstention never inflates the
    index. Framing and Missing Context are closed-book and always present.
    """
    score: float = Field(ge=0, le=10)
    factual_accuracy: float = Field(ge=0, le=10)
    factual_accuracy_label: str = "NEI"          # SUPPORTED | REFUTED | NEI
    factual_accuracy_reasoning: str = ""
    misleading_framing: float = Field(ge=0, le=10)
    misleading_framing_reasoning: str = ""
    missing_context: float = Field(ge=0, le=10)
    missing_context_reasoning: str = ""
    accuracy_counted: bool = True                # False when NEI → out of the mean
    reasoning: str = ""


class FactCheckResult(BaseModel):
    """Aggregated fact-check result for one article (the judge-picked winner)."""
    fact_check_score: float
    fact_check: FactCheckScore
    claims: list[str] = Field(default_factory=list)
    evidence: list[dict] = Field(default_factory=list)   # per-claim evidence bundles
    reasoning: str = ""
    # Deterministic metrics (src/analysis/hard_metrics.py) fed to the prompts
    # as the MESSWERTE block — {"text": ..., "evidence": ...}, persisted for audit.
    hard_metrics: dict = Field(default_factory=dict)
