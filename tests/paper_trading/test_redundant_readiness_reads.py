"""Issue #97 — redundant status/readiness DB read consolidation."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock, patch
from uuid import uuid4

from fastapi.testclient import TestClient
from paper_trading.config import PaperTradingConfig
from paper_trading.enums import RuntimeStatus
from paper_trading.models import RuntimeState
from paper_trading.readiness import ReadinessService

pytest_plugins = ["tests.paper_trading.test_readonly_api"]


def test_status_uses_single_runtime_snapshot(readonly_client: TestClient) -> None:
    repo = readonly_client._repo  # type: ignore[attr-defined]
    repo.get_runtime_state.reset_mock()
    readonly_client.get("/api/v1/status")
    assert repo.get_runtime_state.call_count == 1


def test_evaluate_explicit_none_does_not_fetch_runtime() -> None:
    """runtime=None means missing state — must not re-read the DB (#97 P1)."""
    repo = MagicMock()
    config = MagicMock(spec=PaperTradingConfig)
    config.stale_runtime_threshold_seconds = 60
    config.scheduler_enabled = False
    service = ReadinessService(repo, config)
    snapshot = service.evaluate(market_data_ready=True, runtime=None)
    repo.get_runtime_state.assert_not_called()
    assert snapshot.runtime_readiness is False
    assert "runtime_state_missing" in snapshot.reasons


def test_evaluate_unset_fetches_runtime_once() -> None:
    repo = MagicMock()
    now = datetime.now(UTC)
    runtime = RuntimeState(
        instance_id=uuid4(),
        status=RuntimeStatus.READY,
        heartbeat_at=now,
        version=1,
    )
    repo.get_runtime_state.return_value = runtime
    repo.get_running_scheduler_runs.return_value = ()
    repo.list_permanent_configuration_failures.return_value = ()
    config = MagicMock(spec=PaperTradingConfig)
    config.stale_runtime_threshold_seconds = 3600
    config.scheduler_enabled = False
    service = ReadinessService(repo, config)
    service.evaluate(market_data_ready=True, scheduler_active=True)
    assert repo.get_runtime_state.call_count == 1


def test_status_missing_runtime_stays_stopped_without_second_read(
    readonly_client: TestClient,
) -> None:
    repo = readonly_client._repo  # type: ignore[attr-defined]
    repo.get_runtime_state.return_value = None
    repo.get_runtime_state.reset_mock()
    body = readonly_client.get("/api/v1/status").json()
    assert repo.get_runtime_state.call_count == 1
    assert body["display_status"] == "STOPPED"
    assert body["runtime"] is None
    assert body["readiness"]["runtime_readiness"] is False


def test_runtime_last_error_is_sanitized_in_status(readonly_client: TestClient) -> None:
    repo = readonly_client._repo  # type: ignore[attr-defined]
    now = datetime.now(UTC)
    runtime = RuntimeState(
        instance_id=uuid4(),
        status=RuntimeStatus.READY,
        heartbeat_at=now,
        last_error="invalid api_key secret",
        version=1,
    )
    repo.get_runtime_state.return_value = runtime
    body = readonly_client.get("/api/v1/status").json()
    assert body["runtime"]["last_error"] == "sanitized error"


def test_market_data_skips_full_readiness_evaluate(readonly_client: TestClient) -> None:
    with patch("paper_trading.readonly_api.ReadinessService") as readiness_cls:
        readonly_client.get("/api/v1/market-data")
        readiness_cls.assert_not_called()
