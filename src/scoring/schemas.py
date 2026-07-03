"""
Pydantic schemas for structured LLM output.

Ragebait Index — Is this emotion manufactured or authentic?
                 Blom & Hansen (2015), Potthast et al. (2016), Rony et al. (2017), Brady et al. (2017)
                 Higher = more manufactured. 0 = fully authentic, 10 = pure engagement farming.
"""

from pydantic import BaseModel, Field, model_validator


class PreScoreResult(BaseModel):
    """
    Tier-1 screening result — Mistral Small, title + first ~250 words.
    Single score: likelihood of manufactured emotion / clickbait.
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


class RagebaitScore(BaseModel):
    """
    Blom & Hansen (2015) / Potthast et al. (2016) / Rony et al. (2017) / Brady et al. (2017).
    Measures whether emotional charge is manufactured for engagement
    or emerges authentically from the facts reported.
    Higher = more manufactured. Higher = worse.

    From v7 onward, each sub-score has its own focused reasoning (one API call each).
    """
    score: float = Field(ge=0, le=10)
    curiosity_gap: float = Field(ge=0, le=10)
    curiosity_gap_reasoning: str = ""
    conflict_staging: float = Field(ge=0, le=10)
    conflict_staging_reasoning: str = ""
    emotional_inflation: float = Field(ge=0, le=10)
    emotional_inflation_reasoning: str = ""
    narrative_exploitation: float = Field(ge=0, le=10)
    narrative_exploitation_reasoning: str = ""
    reasoning: str  # combined, kept for backward compatibility


class ScoreResult(BaseModel):
    """Aggregated result written to the DB."""
    ragebait_score: float
    ragebait: RagebaitScore
    reasoning: str
    # Deterministic text metrics (src/analysis/hard_metrics.py) that were fed
    # to the sub-score prompts as the MESSWERTE block — persisted for audit.
    hard_metrics: dict = Field(default_factory=dict)
