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
