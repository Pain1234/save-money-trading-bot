"""Issue #98 — dashboard summary API tests."""

from __future__ import annotations

from fastapi.testclient import TestClient

pytest_plugins = ["tests.paper_trading.test_readonly_api"]


def test_readonly_dashboard_summary_schema(readonly_client: TestClient) -> None:
    body = readonly_client.get("/api/v1/dashboard-summary").json()
    assert body["display_status"] in {"READY", "DEGRADED", "STOPPED"}
    assert "wallet" in body
    assert "open_position_count" in body
    assert "position_summary" in body
    assert "warnings" in body
    assert body["status"]["display_status"] == body["display_status"]
