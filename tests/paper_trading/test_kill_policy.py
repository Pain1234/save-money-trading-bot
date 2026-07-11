"""Kill switch close policy fail-closed behaviour."""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient
from paper_trading.api import app, set_market_data_ready, set_scheduler_active
from paper_trading.config import PaperTradingConfig
from paper_trading.enums import KillSwitchClosePolicy, PaperOrderType, RuntimeStatus
from paper_trading.runtime import RuntimeService

from tests.paper_trading.conftest import _postgres_url, requires_postgres
from tests.paper_trading.e2e.helpers import (
    PaperE2EHarness,
    build_breakout_historical_bundle,
    historical_to_strategy_bundle,
)

pytestmark = [requires_postgres, pytest.mark.postgres]


def test_config_freeze_is_valid() -> None:
    config = PaperTradingConfig(
        database_url="postgresql://localhost/paper",
        kill_switch_close_policy=KillSwitchClosePolicy.FREEZE,
    )
    assert config.kill_switch_close_policy == KillSwitchClosePolicy.FREEZE


def test_config_rejects_close_at_next_open() -> None:
    with pytest.raises(ValueError, match="CLOSE_AT_NEXT_OPEN"):
        PaperTradingConfig(
            database_url="postgresql://localhost/paper",
            kill_switch_close_policy=KillSwitchClosePolicy.CLOSE_AT_NEXT_OPEN,
        )


def test_from_env_rejects_close_at_next_open(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PAPER_KILL_SWITCH_CLOSE_POLICY", "CLOSE_AT_NEXT_OPEN")
    with pytest.raises(ValueError, match="CLOSE_AT_NEXT_OPEN"):
        PaperTradingConfig.from_env()


@pytest.fixture
def control_client(
    db_session,
    e2e_harness: PaperE2EHarness,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setenv("PAPER_TRADING_DATABASE_URL", _postgres_url())
    monkeypatch.setenv("PAPER_CONTROL_API_ENABLED", "true")
    monkeypatch.setenv("PAPER_CONTROL_API_KEY", "policy-test-key")
    monkeypatch.setenv("PAPER_CONTROL_API_RATE_LIMIT_PER_MINUTE", "1000")
    set_market_data_ready(True)
    set_scheduler_active(True)
    from paper_trading import api_dependencies

    app.dependency_overrides[api_dependencies.get_repository] = lambda: e2e_harness.repo
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_api_rejects_close_at_next_open_without_state_change(
    control_client: TestClient,
    e2e_harness: PaperE2EHarness,
) -> None:
    client = control_client
    wallet_before = e2e_harness.repo.get_wallet()
    runtime_before = e2e_harness.repo.get_runtime_state()
    positions_before = len(e2e_harness.repo.list_positions(limit=100))
    orders_before = len(e2e_harness.repo.list_orders(limit=100))

    response = client.post(
        "/control/kill",
        headers={"X-API-Key": "policy-test-key"},
        json={"close_policy": KillSwitchClosePolicy.CLOSE_AT_NEXT_OPEN.value},
    )
    assert response.status_code == 422
    assert "CLOSE_AT_NEXT_OPEN" in response.json()["detail"]

    wallet_after = e2e_harness.repo.get_wallet()
    runtime_after = e2e_harness.repo.get_runtime_state()
    assert wallet_after == wallet_before
    assert runtime_after is not None and runtime_before is not None
    assert runtime_after.kill_switch == runtime_before.kill_switch
    assert len(e2e_harness.repo.list_positions(limit=100)) == positions_before
    assert len(e2e_harness.repo.list_orders(limit=100)) == orders_before

    events = e2e_harness.repo.list_audit_events(limit=20)
    rejected = [e for e in events if e.event_type == "CONTROL_KILL_POLICY_REJECTED"]
    assert rejected
    payload_text = json.dumps(rejected[-1].payload_json)
    assert "CLOSE_AT_NEXT_OPEN" in payload_text
    assert "policy-test-key" not in payload_text


def test_api_kill_freeze_enables_switch(control_client: TestClient, e2e_harness: PaperE2EHarness) -> None:
    client = control_client
    response = client.post(
        "/control/kill",
        headers={"X-API-Key": "policy-test-key"},
        json={"close_policy": KillSwitchClosePolicy.FREEZE.value},
    )
    assert response.status_code == 200
    runtime = e2e_harness.repo.get_runtime_state()
    assert runtime is not None
    assert runtime.kill_switch is True


def test_freeze_does_not_create_exit_orders(
    e2e_harness: PaperE2EHarness,
) -> None:
    harness = e2e_harness
    hist = build_breakout_historical_bundle("BTC")
    bundle, eval_time = historical_to_strategy_bundle(hist, "BTC", daily_count=30)
    harness.evaluate_at_close("BTC", bundle, eval_time)
    RuntimeService(harness.repo).set_kill_switch(True)
    orders = harness.repo.list_orders(limit=100)
    stop_orders = [o for o in orders if o.order_type == PaperOrderType.STOP_MARKET]
    assert not stop_orders


def test_freeze_persists_over_runtime_reset(e2e_harness: PaperE2EHarness) -> None:
    runtime_svc = RuntimeService(e2e_harness.repo)
    runtime_svc.set_kill_switch(True)
    runtime = e2e_harness.repo.get_runtime_state()
    assert runtime is not None
    e2e_harness.repo.update_runtime_state(
        status=RuntimeStatus.READY,
        expected_version=runtime.version,
    )
    runtime = e2e_harness.repo.get_runtime_state()
    assert runtime is not None
    assert runtime.kill_switch is True
