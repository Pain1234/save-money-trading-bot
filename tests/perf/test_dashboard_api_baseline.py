"""Unit tests for dashboard API baseline measurement script (P2.5 / Issue #95)."""

from __future__ import annotations

import json
from pathlib import Path

from scripts.measure_dashboard_api_baseline import (
    DEFAULT_ENDPOINTS,
    SampleStats,
    _percentile,
    _stats,
    build_report,
)


def test_percentile_and_stats() -> None:
    values = [10.0, 20.0, 30.0, 40.0, 100.0]
    stats = _stats(values, [10, 20, 30, 40, 50])
    assert stats.p50_ms == 30.0
    assert stats.max_ms == 100.0
    assert stats.samples == 5
    assert stats.response_bytes_p50 == 30
    assert stats.response_bytes_max == 50
    assert _percentile(values, 95) >= 40.0


def test_baseline_sample_fixture_structure() -> None:
    fixture = Path(__file__).resolve().parents[1] / "fixtures" / "perf" / "baseline-sample.json"
    payload = json.loads(fixture.read_text(encoding="utf-8"))
    assert payload["methodology"]["optimization_applied"] is False
    assert "endpoints" in payload
    assert payload["p25_budgets_ms"]["overview_warm_p95"] == 1500


def test_build_report_uses_default_endpoints(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    calls: list[tuple[str, bool]] = []

    def fake_fetch(base_url: str, path: str, *, cold: bool) -> tuple[float, int]:
        calls.append((path, cold))
        return 12.5, 128

    monkeypatch.setattr(
        "scripts.measure_dashboard_api_baseline._fetch_ms",
        fake_fetch,
    )
    monkeypatch.setattr("scripts.measure_dashboard_api_baseline.time.sleep", lambda _s: None)

    report = build_report(
        base_url="http://127.0.0.1:8080",
        endpoints=DEFAULT_ENDPOINTS[:2],
        cold_runs=1,
        warm_runs=2,
        include_summary=False,
        include_parallel_overview=False,
    )
    assert report["methodology"]["include_dashboard_summary"] is False
    assert report["methodology"]["optimization_applied"] is False
    assert "out_of_scope" in report["methodology"]
    assert report["base_url"] == "http://127.0.0.1:8080"
    assert len(report["endpoints"]) == 2
    warm = report["endpoints"][0]["warm"]
    assert warm["samples"] == 2
    assert warm["response_bytes_p50"] == 128
    assert isinstance(SampleStats(**warm).p50_ms, float)
    assert any(path == "/api/v1/status" for path, _cold in calls)


def test_build_report_parallel_overview_wall_clock(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    calls: list[tuple[tuple[str, ...], bool]] = []

    def fake_parallel(
        base_url: str,
        paths: tuple[str, ...],
        *,
        cold: bool,
    ) -> tuple[float, int]:
        calls.append((paths, cold))
        # Simulated concurrent wall-clock ≈ slower of status/wallet (80ms),
        # not the sum of sequential GETs (120ms).
        return 80.0, 300

    monkeypatch.setattr(
        "scripts.measure_dashboard_api_baseline._fetch_parallel_wall_ms",
        fake_parallel,
    )
    monkeypatch.setattr("scripts.measure_dashboard_api_baseline.time.sleep", lambda _s: None)

    report = build_report(
        base_url="http://127.0.0.1:8080",
        endpoints=(),
        cold_runs=1,
        warm_runs=5,
        include_parallel_overview=True,
    )
    overview = report["endpoints"][0]
    assert overview["name"] == "overview_parallel_status_wallet"
    assert overview["path"] == "/api/v1/status+/api/v1/wallet"
    assert overview["warm"]["p50_ms"] == 80.0
    assert overview["warm"]["response_bytes_p50"] == 300
    assert any("/api/v1/status" in paths and "/api/v1/wallet" in paths for paths, _c in calls)
