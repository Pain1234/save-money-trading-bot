"""Unit tests for Layer C probe region metadata resolution (Issue #121)."""

from __future__ import annotations

from scripts.run_railway_layer_c_probe import resolve_regions


def test_resolve_regions_defaults_api_to_not_measured(monkeypatch) -> None:
    monkeypatch.delenv("LAYER_C_API_REGION", raising=False)
    monkeypatch.delenv("LAYER_C_DASHBOARD_REGION", raising=False)
    monkeypatch.delenv("LAYER_C_POSTGRES_REGION", raising=False)
    regions = resolve_regions()
    assert regions["paper-trading-api"] == "NOT_MEASURED"
    assert regions["paper-trading-dashboard"] == "europe-west4-drams3a"
    assert regions["paper-trading-postgres"] == "europe-west4-drams3a"


def test_resolve_regions_honors_api_region_env(monkeypatch) -> None:
    monkeypatch.setenv("LAYER_C_API_REGION", "europe-west4-drams3a")
    regions = resolve_regions()
    assert regions["paper-trading-api"] == "europe-west4-drams3a"
