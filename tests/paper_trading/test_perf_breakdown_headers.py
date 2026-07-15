"""Tests for opt-in Layer-C residual breakdown headers (Issue #121)."""

from __future__ import annotations

from fastapi.testclient import TestClient
from paper_trading.readonly_api import app


def test_breakdown_headers_absent_by_default(monkeypatch) -> None:
    monkeypatch.delenv("PAPER_API_PERF_BREAKDOWN", raising=False)
    client = TestClient(app)
    response = client.get("/health")
    assert response.status_code == 200
    assert "X-Perf-Engine-Create-Ms" not in response.headers


def test_breakdown_headers_present_when_enabled(monkeypatch) -> None:
    monkeypatch.setenv("PAPER_API_PERF_BREAKDOWN", "1")
    # Health does not use DB session; headers should still be emitted (zeros ok).
    client = TestClient(app)
    response = client.get("/health")
    assert response.status_code == 200
    assert "X-Perf-Engine-Create-Ms" in response.headers
    assert "X-Perf-Session-Setup-Ms" in response.headers
    assert "X-Perf-Pool-Connect-Ms" in response.headers
    assert float(response.headers["X-Perf-Engine-Create-Ms"]) >= 0.0
