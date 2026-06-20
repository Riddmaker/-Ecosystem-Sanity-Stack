"""Unit tests for the shared Mistral client's 429 back-off — no network."""

from src.scoring.llm_client import _retry_after_seconds


class _FakeResp:
    def __init__(self, headers):
        self.headers = headers


class _FakeExc(Exception):
    def __init__(self, headers=None):
        self.raw_response = _FakeResp(headers) if headers is not None else None


def test_retry_after_honours_server_header():
    assert _retry_after_seconds(_FakeExc({"retry-after": "7"}), attempt=0) == 7.0
    # capitalised variant
    assert _retry_after_seconds(_FakeExc({"Retry-After": "3.5"}), attempt=2) == 3.5


def test_retry_after_falls_back_to_exponential():
    # no response / no headers → 5, 10, 20, 40 (capped)
    assert _retry_after_seconds(_FakeExc(None), attempt=0) == 5.0
    assert _retry_after_seconds(_FakeExc({}), attempt=1) == 10.0
    assert _retry_after_seconds(_FakeExc({}), attempt=2) == 20.0
    assert _retry_after_seconds(_FakeExc({}), attempt=9) == 40.0  # cap


def test_retry_after_ignores_non_numeric_header():
    # HTTP-date style value → fall back to back-off
    out = _retry_after_seconds(_FakeExc({"retry-after": "Wed, 21 Oct 2026 07:28:00 GMT"}), attempt=0)
    assert out == 5.0
