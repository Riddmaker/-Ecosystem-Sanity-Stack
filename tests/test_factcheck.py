"""
Unit tests for the fact-check retrieval layer — no network, no API key, no DB.

Covers:
  - Claim extraction parsing + cap (Mistral client mocked).
  - Google Fact Check Tools response parsing + missing-key guard.
  - Tavily response parsing + missing-key guard + exclude_domains wiring.
  - domain_of() host normalisation.
"""

from datetime import datetime, timedelta, timezone

import pytest

from src.factcheck import retrieval
from src.factcheck.claims import ClaimExtractor
from src.factcheck.retrieval import GoogleFactCheckClient, TavilyClient, domain_of
from src.pipeline import _factcheck_due_since


# ── Fake HTTP plumbing ────────────────────────────────────────────────────────

class _FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


# ── domain_of ─────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("url,expected", [
    ("https://www.20min.ch/story/abc-123", "20min.ch"),
    ("https://www.watson.ch/!123", "watson.ch"),
    ("http://nau.ch/news/x", "nau.ch"),
    ("not-a-url", ""),
])
def test_domain_of(url, expected):
    assert domain_of(url) == expected


# ── Claim extraction ──────────────────────────────────────────────────────────

class _FakeMistralClient:
    """Stands in for MistralJSONClient — returns a canned dict, no network."""
    def __init__(self, *_args, **_kwargs):
        pass

    def query_json(self, system, user, retries=4):
        return {"claims": ["  Behauptung A  ", "Behauptung B", "", "Behauptung C", "Behauptung D"]}


def test_claim_extractor_caps_and_strips(monkeypatch):
    monkeypatch.setattr("src.factcheck.claims.MistralJSONClient", _FakeMistralClient)
    ex = ClaimExtractor(api_key="x")
    claims = ex.extract(title="t", content="c", max_claims=3)
    # Blank dropped, whitespace stripped, capped to 3.
    assert claims == ["Behauptung A", "Behauptung B", "Behauptung C"]


# ── Google Fact Check Tools ───────────────────────────────────────────────────

def test_fct_missing_key_returns_empty(monkeypatch):
    monkeypatch.delenv("GOOGLE_FACTCHECK_API_KEY", raising=False)
    client = GoogleFactCheckClient()
    assert client.available is False
    # Must NOT hit the network when no key is configured.
    monkeypatch.setattr(retrieval.requests, "get", _boom)
    assert client.search("irgendeine Behauptung") == []


def test_fct_parses_claim_reviews(monkeypatch):
    payload = {
        "claims": [
            {
                "text": "80 Prozent der Einbrüche gehen auf eine Bande zurück",
                "claimant": "Ein Sicherheitsberater",
                "claimReview": [
                    {
                        "publisher": {"name": "Faktencheck CH", "site": "faktencheck.ch"},
                        "url": "https://faktencheck.ch/x",
                        "title": "Falsche Einbruchsstatistik",
                        "textualRating": "Falsch",
                        "reviewDate": "2026-06-01T00:00:00Z",
                        "languageCode": "de",
                    }
                ],
            }
        ]
    }
    monkeypatch.setattr(retrieval.requests, "get", lambda *a, **k: _FakeResponse(payload))
    client = GoogleFactCheckClient(api_key="dummy")
    reviews = client.search("Einbrüche Bande", language="de")
    assert len(reviews) == 1
    r = reviews[0]
    assert r.publisher == "Faktencheck CH"
    assert r.site == "faktencheck.ch"
    assert r.rating == "Falsch"
    assert r.claimant == "Ein Sicherheitsberater"
    assert r.url == "https://faktencheck.ch/x"


def test_fct_handles_empty_payload(monkeypatch):
    monkeypatch.setattr(retrieval.requests, "get", lambda *a, **k: _FakeResponse({}))
    client = GoogleFactCheckClient(api_key="dummy")
    assert client.search("nichts gefunden") == []


# ── Tavily ────────────────────────────────────────────────────────────────────

def test_tavily_missing_key_returns_empty(monkeypatch):
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    client = TavilyClient()
    assert client.available is False
    monkeypatch.setattr(retrieval.requests, "post", _boom)
    assert client.search("novel claim") == []


def test_tavily_parses_results_and_sends_exclude_domains(monkeypatch):
    captured = {}

    def _fake_post(url, json=None, headers=None, timeout=None):
        captured["url"] = url
        captured["json"] = json
        captured["headers"] = headers
        return _FakeResponse({
            "results": [
                {"title": "Quelle 1", "url": "https://a.example/1",
                 "content": "Beleg eins", "score": 0.91},
                {"title": "Quelle 2", "url": "https://b.example/2",
                 "content": "Beleg zwei", "score": 0.42},
            ]
        })

    monkeypatch.setattr(retrieval.requests, "post", _fake_post)
    client = TavilyClient(api_key="tvly-dummy")
    ev = client.search("eine Behauptung", exclude_domains=["20min.ch"], max_results=5)

    assert [e.title for e in ev] == ["Quelle 1", "Quelle 2"]
    assert ev[0].score == 0.91
    # Request wiring: Bearer auth, basic depth (1 credit), own-domain excluded.
    assert captured["headers"]["Authorization"] == "Bearer tvly-dummy"
    assert captured["json"]["search_depth"] == "basic"
    assert captured["json"]["exclude_domains"] == ["20min.ch"]
    assert captured["url"] == retrieval.TAVILY_URL


def _boom(*_a, **_k):  # pragma: no cover - only called if a guard fails
    raise AssertionError("network call made despite missing API key")


# ── Evidence rendering ────────────────────────────────────────────────────────

def test_render_evidence_empty():
    from src.factcheck.scorer import render_evidence
    assert "KEINE EXTERNEN BELEGE" in render_evidence([])


def test_render_evidence_includes_verdict_and_web():
    from src.factcheck.scorer import render_evidence
    block = render_evidence([{
        "claim": "Behauptung X",
        "fact_checks": [{"rating": "Falsch", "publisher": "FC CH", "title": "T", "url": "u"}],
        "web_evidence": [{"score": 0.9, "title": "W", "content": "Beleg", "url": "u2"}],
    }])
    assert "Behauptung X" in block
    assert "Falsch" in block and "FC CH" in block
    assert "Beleg" in block


# ── FactCheckScorer (Large client mocked) ─────────────────────────────────────

class _FakeLargeClient:
    """Dispatches a canned dict per sub-score by sniffing the system prompt."""
    accuracy = {"label": "NEI", "score": 0, "reasoning": "nei"}

    def __init__(self, *_a, **_k):
        pass

    def query_json(self, system, user, retries=4):
        if "FACTUAL ACCURACY" in system:
            return dict(_FakeLargeClient.accuracy)
        if "MISLEADING FRAMING" in system:
            return {"score": 6, "reasoning": "framing"}
        if "MISSING CONTEXT" in system:
            return {"score": 4, "reasoning": "context"}
        if "Chef vom Dienst" in system:
            return {"chosen": 99, "reasoning": "judge"}
        if "Redakteur" in system:   # reader service
            return {"facts": "fakten", "stake": "stake", "action": {"a": "tu dies", "b": "und das"}}
        return {}


def _scorer(monkeypatch):
    monkeypatch.setattr("src.factcheck.scorer.MistralJSONClient", _FakeLargeClient)
    from src.factcheck.scorer import FactCheckScorer
    return FactCheckScorer(api_key="x")


def test_score_excludes_nei_accuracy_from_mean(monkeypatch):
    _FakeLargeClient.accuracy = {"label": "NEI", "score": 0, "reasoning": "nei"}
    scorer = _scorer(monkeypatch)
    res = scorer.score(title="t", content="c", claims=["x"], evidence=[])
    # NEI → accuracy excluded; mean of framing(6) + context(4) = 5.0
    assert res.fact_check.accuracy_counted is False
    assert res.fact_check_score == 5.0


def test_score_counts_refuted_accuracy_in_mean(monkeypatch):
    _FakeLargeClient.accuracy = {"label": "REFUTED", "score": 9, "reasoning": "r"}
    scorer = _scorer(monkeypatch)
    res = scorer.score(title="t", content="c", claims=["x"], evidence=[])
    # REFUTED → mean of (6 + 4 + 9) / 3 = 6.333…
    assert res.fact_check.accuracy_counted is True
    assert round(res.fact_check_score, 2) == 6.33


def test_score_invalid_label_falls_back_to_nei(monkeypatch):
    _FakeLargeClient.accuracy = {"label": "BOGUS", "score": 8, "reasoning": "?"}
    scorer = _scorer(monkeypatch)
    res = scorer.score(title="t", content="c", claims=["x"], evidence=[])
    assert res.fact_check.factual_accuracy_label == "NEI"
    assert res.fact_check.accuracy_counted is False


def test_score_coerces_dict_reasoning_to_string(monkeypatch):
    # Mistral sometimes returns reasoning as a nested object — must not crash.
    monkeypatch.setattr("src.factcheck.scorer.MistralJSONClient", _FakeLargeClient)
    from src.factcheck.scorer import FactCheckScorer
    import src.factcheck.scorer as scorer_mod

    def dict_reasoning(self, system, user, retries=4):
        if "MISSING CONTEXT" in system:
            return {"score": 7, "reasoning": {"eindruck": "verzerrt", "fehlt": "Kontext"}}
        if "MISLEADING FRAMING" in system:
            return {"score": 6, "reasoning": ["teil eins", "teil zwei"]}
        if "FACTUAL ACCURACY" in system:
            return {"label": "NEI", "score": 0, "reasoning": "nei"}
        return {}

    monkeypatch.setattr(scorer_mod.MistralJSONClient, "query_json", dict_reasoning, raising=False)
    res = FactCheckScorer(api_key="x").score(title="t", content="c", claims=["x"], evidence=[])
    assert isinstance(res.fact_check.missing_context_reasoning, str)
    assert "verzerrt" in res.fact_check.missing_context_reasoning
    assert isinstance(res.fact_check.misleading_framing_reasoning, str)
    assert "teil eins" in res.fact_check.misleading_framing_reasoning


def test_judge_clamps_out_of_range_choice(monkeypatch):
    _FakeLargeClient.accuracy = {"label": "NEI", "score": 0, "reasoning": "nei"}
    scorer = _scorer(monkeypatch)
    verdict = scorer.judge_candidates([
        {"title": "a", "fc_pre_score": 5}, {"title": "b", "fc_pre_score": 4},
        {"title": "c", "fc_pre_score": 3},
    ])
    assert verdict["chosen"] == 3   # raw 99 clamped to N=3


def test_fact_check_to_db_fields_shape(monkeypatch):
    _FakeLargeClient.accuracy = {"label": "REFUTED", "score": 9, "reasoning": "r"}
    scorer = _scorer(monkeypatch)
    from src.factcheck.scorer import fact_check_to_db_fields
    res = scorer.score(title="t", content="c", claims=["x"], evidence=[{"claim": "x"}])
    fields = fact_check_to_db_fields(res, judge_reasoning="because")
    assert set(fields) == {
        "fact_check_score", "fact_check_details",
        "fact_check_model", "fact_check_version", "fact_check_at",
    }
    assert fields["fact_check_details"]["sub_scores"]["factual_accuracy_label"] == "REFUTED"
    assert fields["fact_check_details"]["judge_reasoning"] == "because"


def test_generate_reader_service_coerces_dict_action(monkeypatch):
    _FakeLargeClient.accuracy = {"label": "NEI", "score": 0, "reasoning": "nei"}
    scorer = _scorer(monkeypatch)
    res = scorer.score(title="t", content="c", claims=["x"], evidence=[])
    rs = scorer.generate_reader_service(title="t", content="c", result=res)
    assert set(rs) == {"facts", "stake", "action"}
    # dict action flattened to a string
    assert isinstance(rs["action"], str)
    assert "tu dies" in rs["action"] and "und das" in rs["action"]


# ── Frontend reasoning shortening ─────────────────────────────────────────────

def test_clip_reasoning_shortens_and_honours_arrow():
    from src.frontend.components import clip_reasoning
    # short text returned as-is
    assert clip_reasoning("kurz und knapp") == "kurz und knapp"
    # arrow verdict preferred
    assert clip_reasoning("PF=Ja, UQ=Ja → Das ist das Urteil.") == "Das ist das Urteil."
    # long text trimmed under the limit, never mid-word, with ellipsis or sentence end
    long = "Erster Satz ist hier. " + ("wort " * 80)
    out = clip_reasoning(long, limit=60)
    assert len(out) <= 64
    assert out.startswith("Erster Satz ist hier.")


# ── Cadence gate (pipeline orchestration) ─────────────────────────────────────

def test_cadence_always_due_when_disabled_or_first_run():
    now = datetime(2026, 6, 20, 12, 0, tzinfo=timezone.utc)
    # cadence effectively off
    assert _factcheck_due_since(now - timedelta(hours=1), now, 1) is True
    # nothing has run yet
    assert _factcheck_due_since(None, now, 6) is True


def test_cadence_skips_within_window_runs_after():
    now = datetime(2026, 6, 20, 12, 0, tzinfo=timezone.utc)
    # last run 2h ago, cadence 6h → not due yet
    assert _factcheck_due_since(now - timedelta(hours=2), now, 6) is False
    # last run 6h ago → due (>= 6 - 0.5)
    assert _factcheck_due_since(now - timedelta(hours=6), now, 6) is True
    # 5.5h ago hits the slack boundary exactly → due
    assert _factcheck_due_since(now - timedelta(hours=5, minutes=30), now, 6) is True
