"""
Pydantic schemas for structured LLM output.

Two scores, two questions:

  Ragebait Index   — Is this emotion manufactured or authentic?
                     Blom & Hansen (2015), Potthast et al. (2016), Rony et al. (2017)
                     Higher = more manufactured. 0 = fully authentic, 10 = pure engagement farming.

  Emotional Weight — How heavy is this content to process?
                     Neutral descriptor. No value judgment.
                     Low does NOT mean good. High does NOT mean bad.
                     Context for interpreting the Ragebait Index.
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
    """
    score: float = Field(ge=0, le=10)
    curiosity_gap: float = Field(ge=0, le=10)           # Headline withholds info honest reporting would give
    conflict_staging: float = Field(ge=0, le=10)        # Artificial conflict between groups/people
    emotional_inflation: float = Field(ge=0, le=10)     # Emotional claims not backed by concrete facts
    narrative_exploitation: float = Field(ge=0, le=10)  # Real story packaged as outrage-trigger (villain/victim/injustice)
    reasoning: str


class EmotionalWeightScore(BaseModel):
    """
    Neutral descriptor. Measures how emotionally demanding this content is to process.
    Not a quality signal — purely contextual.
    High weight + low ragebait = authentic heavy news (legitimate, but take breaks).
    High weight + high ragebait = exploitation of heavy topics for clicks (worst pattern).
    Low weight + low ragebait = clean informational content (ideal).
    Low weight + high ragebait = pure manufactured clickbait (no substance).
    """
    score: float = Field(ge=0, le=10)
    topic_gravity: float = Field(ge=0, le=10)      # How serious/significant is the subject matter?
    emotional_exposure: float = Field(ge=0, le=10) # How much raw emotion does the reader encounter?
    reader_burden: float = Field(ge=0, le=10)      # Overall psychological processing demand
    reasoning: str


class ScoreResult(BaseModel):
    """Aggregated result written to the DB."""
    ragebait_score: float          # primary signal: manufactured emotion (higher = worse)
    emotional_weight: float        # neutral context: how heavy is this content?
    ragebait: RagebaitScore
    emotional_weight_detail: EmotionalWeightScore
    reasoning: str
