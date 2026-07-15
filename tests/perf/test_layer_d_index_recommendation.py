"""Unit tests for Layer D index recommendation gate (Issue #101)."""

from __future__ import annotations

from scripts.audit_dashboard_sql_explain import PlanMetrics, _index_recommendation


def _plan(status: str, execution_ms: float | None) -> PlanMetrics:
    return PlanMetrics(status=status, execution_ms=execution_ms)


def test_index_recommendation_uses_slower_of_first_and_cursor() -> None:
    first = _plan("MEASURED", 0.1)
    cursor = _plan("MEASURED", 200.0)
    result = _index_recommendation(first, cursor, route_latency_ms=2400.0)
    assert result["recommendation_status"] == "FOLLOW_UP_REQUIRED"
    assert "200.000" in result["recommendation"]


def test_index_recommendation_no_action_when_share_below_threshold() -> None:
    first = _plan("MEASURED", 0.08)
    cursor = _plan("MEASURED", 0.12)
    result = _index_recommendation(first, cursor, route_latency_ms=2400.0)
    assert result["recommendation_status"] == "NO_ACTION"
    assert "0.0050%" in result["recommendation"] or "0.005%" in result["recommendation"]


def test_index_recommendation_without_route_latency_does_not_claim_relative() -> None:
    first = _plan("MEASURED", 0.05)
    cursor = _plan("NOT_MEASURED", None)
    result = _index_recommendation(first, cursor)
    assert result["recommendation_status"] == "NO_ACTION"
    assert "not a relative share claim" in result["recommendation"]


def test_index_recommendation_ignores_unmeasured_cursor() -> None:
    first = _plan("MEASURED", 0.05)
    cursor = _plan("NOT_MEASURED", None)
    result = _index_recommendation(first, cursor, route_latency_ms=2500.0)
    assert result["recommendation_status"] == "NO_ACTION"
