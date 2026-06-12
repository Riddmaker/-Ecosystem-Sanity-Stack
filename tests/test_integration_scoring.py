"""
Integration tests for the two-tier scoring pipeline — requires MISTRAL_API_KEY.

What these tests verify:
  1. PreScorer returns a valid score and reasoning for a real article snippet
  2. MediaScorer returns all four sub-scores in range
  3. Composite ragebait_score is the mean of the four sub-scores
  4. gate_article() returns a dict with 'pass' and 'reasoning' keys
  5. judge_articles() picks a valid winner index from a list of candidates

Run:
  pytest tests/test_integration_scoring.py -m integration -v
"""

import pytest
from tests.conftest import skip_no_api_key

# Short, real-feeling German article fixture — no network needed
SAMPLE_TITLE = "Bundesrat erhöht Steuern für Reiche – Widerstand aus der Wirtschaft"
SAMPLE_CONTENT = (
    "Der Bundesrat hat heute eine Erhöhung der Vermögenssteuer für Haushalte "
    "mit einem Vermögen von über einer Million Franken angekündigt. "
    "Wirtschaftsverbände reagierten mit scharfer Kritik. "
    "«Diese Massnahme wird Investitionen abwürgen und Arbeitsplätze kosten», "
    "sagte Economiesuisse-Präsident Hans Muster. "
    "Die Linke begrüsste den Schritt als längst überfällig. "
    "Der Entscheid tritt per 1. Januar 2026 in Kraft und betrifft schätzungsweise "
    "120'000 Haushalte in der Schweiz."
)


@pytest.mark.integration
@skip_no_api_key
class TestPreScorerIntegration:

    def test_returns_valid_score(self, pre_scorer):
        """PreScorer returns a score in [0, 10] with non-empty reasoning."""
        from src.scoring.schemas import PreScoreResult

        result = pre_scorer.score(title=SAMPLE_TITLE, content=SAMPLE_CONTENT)

        assert isinstance(result, PreScoreResult)
        assert 0 <= result.score <= 10
        assert len(result.reasoning) > 0

    def test_low_score_for_factual_article(self, pre_scorer):
        """A neutral factual article should score below 6."""
        result = pre_scorer.score(title=SAMPLE_TITLE, content=SAMPLE_CONTENT)
        assert result.score < 6, (
            f"Expected low pre-score for factual article, got {result.score}. "
            f"Reasoning: {result.reasoning}"
        )

    def test_high_score_for_clickbait(self, pre_scorer):
        """An obvious clickbait headline should score above 5."""
        result = pre_scorer.score(
            title="Du wirst nicht glauben, was dieser Politiker heute gesagt hat!",
            content=(
                "Politiker X hat erneut für Empörung gesorgt. "
                "Die Community ist gespalten. Wer hat Recht? "
                "Klick hier für die unglaubliche Wahrheit!"
            ),
        )
        assert result.score > 5, (
            f"Expected high pre-score for clickbait article, got {result.score}. "
            f"Reasoning: {result.reasoning}"
        )


@pytest.mark.integration
@skip_no_api_key
class TestMediaScorerIntegration:

    def test_returns_all_sub_scores(self, media_scorer):
        """MediaScorer returns all four sub-scores in valid range."""
        result = media_scorer.score(title=SAMPLE_TITLE, content=SAMPLE_CONTENT)

        assert 0 <= result.ragebait_score <= 10
        assert 0 <= result.ragebait.curiosity_gap <= 10
        assert 0 <= result.ragebait.conflict_staging <= 10
        assert 0 <= result.ragebait.emotional_inflation <= 10
        assert 0 <= result.ragebait.narrative_exploitation <= 10

    def test_composite_is_mean_of_sub_scores(self, media_scorer):
        """ragebait_score should equal the mean of the four sub-scores (within tolerance)."""
        result = media_scorer.score(title=SAMPLE_TITLE, content=SAMPLE_CONTENT)

        sub_scores = [
            result.ragebait.curiosity_gap,
            result.ragebait.conflict_staging,
            result.ragebait.emotional_inflation,
            result.ragebait.narrative_exploitation,
        ]
        expected_mean = sum(sub_scores) / len(sub_scores)
        assert abs(result.ragebait_score - expected_mean) < 0.6, (
            f"ragebait_score {result.ragebait_score} deviates from sub-score mean "
            f"{expected_mean:.2f} by more than 0.6"
        )

    def test_all_reasonings_present(self, media_scorer):
        """Each sub-score should come with a non-empty reasoning string."""
        result = media_scorer.score(title=SAMPLE_TITLE, content=SAMPLE_CONTENT)

        assert len(result.ragebait.curiosity_gap_reasoning) > 0
        assert len(result.ragebait.conflict_staging_reasoning) > 0
        assert len(result.ragebait.emotional_inflation_reasoning) > 0
        assert len(result.ragebait.narrative_exploitation_reasoning) > 0

    def test_gate_article_returns_verdict(self, media_scorer):
        """gate_article() returns a dict with boolean 'pass' and string 'reasoning'."""
        gate = media_scorer.gate_article(title=SAMPLE_TITLE, content=SAMPLE_CONTENT)

        assert "pass" in gate
        assert isinstance(gate["pass"], bool)
        assert "reasoning" in gate
        assert len(gate["reasoning"]) > 0

    def test_judge_picks_valid_winner(self, media_scorer):
        """judge_articles() returns a 1-indexed winner within the candidate list."""
        candidates = [
            {
                "title": SAMPLE_TITLE,
                "ragebait_score": 4.5,
                "curiosity_gap": 3.0,
                "conflict_staging": 5.0,
                "emotional_inflation": 4.0,
                "narrative_exploitation": 6.0,
                "reasoning": "Mild conflict staging between economic groups.",
            },
            {
                "title": "Bundesrat: Steuerpläne sorgen für hitzige Debatte",
                "ragebait_score": 6.0,
                "curiosity_gap": 5.0,
                "conflict_staging": 7.0,
                "emotional_inflation": 6.0,
                "narrative_exploitation": 6.0,
                "reasoning": "Stronger framing of opposition as conflict.",
            },
        ]
        result = media_scorer.judge_articles(candidates)

        assert "chosen" in result
        assert 1 <= result["chosen"] <= len(candidates)
        assert "reasoning" in result
        assert len(result["reasoning"]) > 0
