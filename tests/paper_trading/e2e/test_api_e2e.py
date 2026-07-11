"""FastAPI E2E against real PostgreSQL trade state."""

from __future__ import annotations

import json
import re
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from paper_trading.api import app, set_market_data_ready, set_scheduler_active
from paper_trading.enums import RuntimeStatus

from tests.paper_trading.conftest import _postgres_url, requires_postgres
from tests.paper_trading.e2e.helpers import (
    PaperE2EHarness,
    build_extended_lifecycle_bundle,
    candle_at,
    fill_context_for_bundle,
    historical_to_strategy_bundle,
)

pytestmark = [requires_postgres, pytest.mark.postgres]

DECIMAL_PATTERN = re.compile(r"^-?\d+(\.\d+)?([eE][+-]?\d+)?$")
UTC_Z_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?Z$")


@pytest.fixture
def api_e2e_client(
    db_session,
    e2e_harness: PaperE2EHarness,
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[TestClient]:
    monkeypatch.setenv("PAPER_TRADING_DATABASE_URL", _postgres_url())
    monkeypatch.setenv("PAPER_CONTROL_API_ENABLED", "true")
    monkeypatch.setenv("PAPER_CONTROL_API_KEY", "e2e-test-key")
    monkeypatch.setenv("PAPER_CONTROL_API_RATE_LIMIT_PER_MINUTE", "1000")

    harness = e2e_harness
    symbol = "BTC"
    hist = build_extended_lifecycle_bundle(symbol)
    bundle, eval_time = historical_to_strategy_bundle(hist, symbol, daily_count=30)
    harness.evaluate_at_close(symbol, bundle, eval_time)
    fill_candle = candle_at(hist, symbol, 30)
    harness.fill_at_open(
        process_time=fill_candle.open_time,
        symbol_contexts={symbol: fill_context_for_bundle(bundle, eval_time, fill_candle)},
    )

    set_market_data_ready(True)
    set_scheduler_active(True)

    from paper_trading import api_dependencies

    app.dependency_overrides[api_dependencies.get_repository] = lambda: harness.repo
    yield TestClient(app)
    app.dependency_overrides.clear()


def _assert_no_secrets(text: str) -> None:
    lowered = text.lower()
    assert "e2e-test-key" not in text
    assert "postgresql" not in lowered or "database_url" not in lowered
    assert "password" not in lowered
    assert "traceback" not in lowered
    assert "PAPER_CONTROL" not in text


def _assert_decimal_strings(obj: object) -> None:
    if isinstance(obj, dict):
        for key, value in obj.items():
            if key in {
                "cash",
                "margin_used",
                "equity",
                "unrealized_pnl",
                "realized_pnl",
                "total_open_risk",
                "quantity",
                "average_entry_price",
                "initial_stop",
                "current_stop",
                "highest_close_since_entry",
                "entry_atr14",
                "margin_reserved",
                "requested_entry",
                "requested_stop",
                "requested_quantity",
                "remaining_quantity",
                "market_open_price",
                "slippage",
                "fill_price",
                "fee",
            }:
                if value is not None:
                    assert isinstance(value, str), f"{key} must be string"
                    assert DECIMAL_PATTERN.match(value), f"{key}={value}"
            _assert_decimal_strings(value)
    elif isinstance(obj, list):
        for item in obj:
            _assert_decimal_strings(item)


def _assert_utc_z(obj: object) -> None:
    if isinstance(obj, dict):
        for key, value in obj.items():
            if key == "payload_json":
                continue
            if key.endswith("_at") or key.endswith("_time") or key == "evaluation_time":
                if value is not None and isinstance(value, str):
                    assert UTC_Z_PATTERN.match(value) or value.endswith("+00:00"), (
                        f"{key}={value}"
                    )
            _assert_utc_z(value)
    elif isinstance(obj, list):
        for item in obj:
            _assert_utc_z(item)


def test_api_read_endpoints_after_trade(api_e2e_client: TestClient) -> None:
    client = api_e2e_client
    endpoints = [
        "/health",
        "/readiness",
        "/runtime",
        "/portfolio",
        "/positions",
        "/intents",
        "/orders",
        "/fills",
        "/evaluations",
        "/audit-events",
        "/scheduler-runs",
    ]
    for path in endpoints:
        response = client.get(path)
        assert response.status_code in {200, 503}, path
        _assert_no_secrets(response.text)
        body = response.json()
        _assert_decimal_strings(body)
        _assert_utc_z(body)

    runtime = client.get("/runtime").json()
    assert runtime["status"] == RuntimeStatus.READY.value

    positions = client.get("/positions", params={"limit": 10}).json()
    assert len(positions["items"]) >= 1
    position_id = positions["items"][0]["position_id"]
    detail = client.get(f"/positions/{position_id}")
    assert detail.status_code == 200
    assert detail.json()["position_id"] == position_id


def test_api_pagination_stable(api_e2e_client: TestClient) -> None:
    client = api_e2e_client
    first = client.get("/fills", params={"limit": 1}).json()
    assert len(first["items"]) == 1
    first_id = first["items"][0]["fill_id"]
    if first.get("next_cursor"):
        second = client.get(
            "/fills",
            params={"limit": 1, "cursor": first["next_cursor"]},
        ).json()
        if second["items"]:
            assert second["items"][0]["fill_id"] != first_id
    again = client.get("/fills", params={"limit": 1}).json()
    assert again["items"][0]["fill_id"] == first_id


def test_api_readiness_503_when_market_data_down(
    api_e2e_client: TestClient,
) -> None:
    set_market_data_ready(False)
    response = api_e2e_client.get("/readiness")
    assert response.status_code == 503
    body = response.json()
    assert body["entry_readiness"] is False
    set_market_data_ready(True)


def test_api_control_disabled_by_default(
    db_session,
    e2e_harness: PaperE2EHarness,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PAPER_TRADING_DATABASE_URL", _postgres_url())
    monkeypatch.setenv("PAPER_CONTROL_API_ENABLED", "false")
    monkeypatch.setenv("PAPER_CONTROL_API_KEY", "e2e-test-key")
    from paper_trading import api_dependencies

    app.dependency_overrides[api_dependencies.get_repository] = lambda: e2e_harness.repo
    client = TestClient(app)
    response = client.post("/control/pause", headers={"X-API-Key": "e2e-test-key"})
    assert response.status_code == 404
    app.dependency_overrides.clear()


def test_api_control_pause_and_resume(api_e2e_client: TestClient) -> None:
    client = api_e2e_client
    pause = client.post("/control/pause", headers={"X-API-Key": "e2e-test-key"})
    assert pause.status_code == 200
    assert pause.json()["accepted"] is True
    runtime = client.get("/runtime").json()
    assert runtime["paused"] is True
    resume = client.post("/control/resume", headers={"X-API-Key": "e2e-test-key"})
    assert resume.status_code == 200
    runtime = client.get("/runtime").json()
    assert runtime["paused"] is False


def test_api_wrong_key_audited_not_stored(api_e2e_client: TestClient) -> None:
    client = api_e2e_client
    before = len(client.get("/audit-events", params={"limit": 100}).json()["items"])
    response = client.post("/control/pause", headers={"X-API-Key": "wrong-key-value"})
    assert response.status_code == 403
    _assert_no_secrets(response.text)
    after_items = client.get("/audit-events", params={"limit": 100}).json()["items"]
    assert len(after_items) == before
    for event in after_items:
        payload = json.dumps(event.get("payload_json", {}))
        assert "wrong-key-value" not in payload


def test_api_run_cycle_idempotent(api_e2e_client: TestClient) -> None:
    client = api_e2e_client
    body = {
        "job_name": "readiness_check",
        "scheduled_for": "2024-06-01T00:00:00Z",
    }
    first = client.post(
        "/control/run-cycle",
        headers={"X-API-Key": "e2e-test-key"},
        json=body,
    )
    second = client.post(
        "/control/run-cycle",
        headers={"X-API-Key": "e2e-test-key"},
        json=body,
    )
    assert first.status_code == 200
    assert second.status_code == 200
    assert "deduplicated" in second.json()["message"] or second.json()["accepted"]
