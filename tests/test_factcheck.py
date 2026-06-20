"""
Unit tests for the fact-check retrieval layer — no network, no API key, no DB.

Covers:
  - Claim extraction parsing + cap (Mistral client mocked).
  - Google Fact Check Tools response parsing + missing-key guard.
  - Tavily response parsing + missing-key guard + exclude_domains wiring.
  - domain_of() host normalisation.
"""

import pytest

from src.factcheck import retrieval
from src.factcheck.claims import ClaimExtractor
from src.factcheck.retrieval import GoogleFactCheckClient, TavilyClient, domain_of


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
