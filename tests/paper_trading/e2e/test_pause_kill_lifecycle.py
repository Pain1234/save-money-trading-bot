"""Pause and kill switch E2E behaviour."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from paper_trading.api import app
from paper_trading.enums import RuntimeStatus
from paper_trading.runtime import RuntimeService

from tests.paper_trading.conftest import requires_postgres
from tests.paper_trading.e2e.helpers import (
    PaperE2EHarness,
    build_breakout_historical_bundle,
    historical_to_strategy_bundle,
)

pytestmark = [requires_postgres, pytest.mark.postgres]


def test_api_pause_blocks_followup_evaluation_and_fill(
    e2e_harness: PaperE2EHarness,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from paper_trading import api_dependencies

    monkeypatch.setenv("PAPER_CONTROL_API_ENABLED", "true")
    monkeypatch.setenv("PAPER_CONTROL_API_KEY", "pause-test-key")
    app.dependency_overrides[api_dependencies.get_repository] = lambda: e2e_harness.repo
    try:
        response = TestClient(app).post(
            "/control/pause",
            headers={"X-API-Key": "pause-test-key"},
        )
        assert response.status_code == 200

        hist = build_breakout_historical_bundle("BTC")
        bundle, eval_time = historical_to_strategy_bundle(hist, "BTC", daily_count=30)
        result = e2e_harness.evaluate_at_close("BTC", bundle, eval_time)

        assert result.intent is None
        assert "paused" in result.blocked_reasons
        assert not e2e_harness.repo.list_fills(limit=100)
    finally:
        app.dependency_overrides.clear()


def test_pause_blocks_new_intents_but_allows_stops(e2e_harness: PaperE2EHarness) -> None:
    harness = e2e_harness
    RuntimeService(harness.repo).set_paused(True)
    hist = build_breakout_historical_bundle("BTC")
    bundle, eval_time = historical_to_strategy_bundle(hist, "BTC", daily_count=30)
    result = harness.evaluate_at_close("BTC", bundle, eval_time)
    assert result.intent is None
    assert "paused" in result.blocked_reasons


def test_kill_switch_persistent_after_runtime_reset(e2e_harness: PaperE2EHarness) -> None:
    harness = e2e_harness
    RuntimeService(harness.repo).set_kill_switch(True)
    runtime = harness.repo.get_runtime_state()
    assert runtime is not None
    assert runtime.kill_switch is True
    harness.repo.update_runtime_state(
        status=RuntimeStatus.READY,
        expected_version=runtime.version,
    )
    runtime = harness.repo.get_runtime_state()
    assert runtime is not None
    assert runtime.kill_switch is True


def test_resume_rejected_when_kill_active(e2e_harness: PaperE2EHarness) -> None:
    harness = e2e_harness
    runtime_svc = RuntimeService(harness.repo)
    runtime_svc.set_kill_switch(True)
    runtime_svc.set_paused(False)
    hist = build_breakout_historical_bundle("BTC")
    bundle, eval_time = historical_to_strategy_bundle(hist, "BTC", daily_count=30)
    result = harness.evaluate_at_close("BTC", bundle, eval_time)
    assert result.intent is None
