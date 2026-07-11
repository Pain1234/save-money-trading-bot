"""Tests for composite readiness."""

from __future__ import annotations

from datetime import timedelta
from unittest.mock import MagicMock
from uuid import uuid4

from paper_trading.clock import FixedClock
from paper_trading.config import PaperTradingConfig
from paper_trading.enums import RuntimeStatus
from paper_trading.lock import InMemoryAdvisoryLock
from paper_trading.models import RuntimeState
from paper_trading.readiness import ReadinessService

from tests.paper_trading.conftest_execution import utc_dt


def _config() -> PaperTradingConfig:
    return PaperTradingConfig.from_env(
        database_url="postgresql://postgres:postgres@localhost:5432/paper_trading_test"
    )


def test_market_data_not_ready_blocks_entry() -> None:
    repo = MagicMock()
    now = utc_dt(2024, 1, 16)
    repo.get_runtime_state.return_value = RuntimeState(
        instance_id=uuid4(),
        status=RuntimeStatus.READY,
        heartbeat_at=now,
        version=1,
    )
    repo.get_running_scheduler_runs.return_value = ()
    service = ReadinessService(repo, _config(), clock=FixedClock(now))
    snap = service.evaluate(market_data_ready=False, scheduler_active=True)
    assert snap.entry_readiness is False
    assert "market_data_not_ready" in snap.reasons


def test_pause_blocks_entry_stops_allowed() -> None:
    repo = MagicMock()
    now = utc_dt(2024, 1, 16)
    repo.get_runtime_state.return_value = RuntimeState(
        instance_id=uuid4(),
        status=RuntimeStatus.READY,
        heartbeat_at=now,
        paused=True,
        version=1,
    )
    repo.get_running_scheduler_runs.return_value = ()
    service = ReadinessService(repo, _config(), clock=FixedClock(now))
    snap = service.evaluate(market_data_ready=True, scheduler_active=True)
    assert snap.entry_readiness is False
    assert service.stops_allowed_when_paused() is True


def test_stale_heartbeat_blocks_readiness() -> None:
    repo = MagicMock()
    old = utc_dt(2024, 1, 16)
    repo.get_runtime_state.return_value = RuntimeState(
        instance_id=uuid4(),
        status=RuntimeStatus.READY,
        heartbeat_at=old,
        version=1,
    )
    repo.get_running_scheduler_runs.return_value = ()
    service = ReadinessService(
        repo,
        _config(),
        clock=FixedClock(old + timedelta(seconds=400)),
    )
    snap = service.evaluate(market_data_ready=True, scheduler_active=True)
    assert "stale_heartbeat" in snap.reasons


def test_advisory_lock_required() -> None:
    repo = MagicMock()
    now = utc_dt(2024, 1, 16)
    repo.get_runtime_state.return_value = RuntimeState(
        instance_id=uuid4(),
        status=RuntimeStatus.READY,
        heartbeat_at=now,
        version=1,
    )
    repo.get_running_scheduler_runs.return_value = ()
    lock = InMemoryAdvisoryLock("a")
    service = ReadinessService(repo, _config(), clock=FixedClock(now))
    snap = service.evaluate(
        market_data_ready=True,
        advisory_lock=lock,
        scheduler_active=True,
    )
    assert "advisory_lock_not_held" in snap.reasons
    lock.try_acquire()
    try:
        snap2 = service.evaluate(
            market_data_ready=True,
            advisory_lock=lock,
            scheduler_active=True,
        )
        assert snap2.runtime_readiness is True
    finally:
        lock.release()
        InMemoryAdvisoryLock.reset()
