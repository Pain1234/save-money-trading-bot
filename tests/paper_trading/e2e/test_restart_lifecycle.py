"""Restart and recovery E2E at transaction boundaries."""

from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

import pytest
from paper_trading.db.orm import SchedulerRunRow
from paper_trading.enums import RuntimeStatus, SchedulerRunStatus
from paper_trading.lock import InMemoryAdvisoryLock
from paper_trading.recovery import recover_on_startup

from tests.paper_trading.conftest import _postgres_url, requires_postgres
from tests.paper_trading.conftest_execution import utc_dt
from tests.paper_trading.e2e.helpers import (
    PaperE2EHarness,
    build_breakout_historical_bundle,
    candle_at,
    fill_context_for_bundle,
    historical_to_strategy_bundle,
    paper_config_from_env,
)

pytestmark = [requires_postgres, pytest.mark.postgres]


def test_recovery_after_orphan_scheduler_run(db_session) -> None:
    from paper_trading.repository import PaperTradingRepository

    repo = PaperTradingRepository(db_session)
    scheduled = utc_dt(2024, 3, 1)
    repo.session.add(
        SchedulerRunRow(
            run_id=uuid4(),
            job_name="daily_signal_evaluation",
            scheduled_for=scheduled,
            started_at=scheduled,
            status=SchedulerRunStatus.RUNNING.value,
            idempotency_key="e2e-orphan",
        )
    )
    repo.session.flush()
    config = paper_config_from_env(_postgres_url())
    lock = InMemoryAdvisoryLock("restart-e2e")
    lock.try_acquire()
    result = recover_on_startup(repo, config, lock, market_data_ready=True)
    assert result.final_status == RuntimeStatus.READY
    assert repo.get_running_scheduler_runs() == ()


def test_crash_after_intent_no_duplicate_on_retry(e2e_harness: PaperE2EHarness) -> None:
    harness = e2e_harness
    hist = build_breakout_historical_bundle("BTC")
    bundle, eval_time = historical_to_strategy_bundle(hist, "BTC", daily_count=30)
    nested = harness.repo.session.begin_nested()
    harness.evaluate_at_close("BTC", bundle, eval_time)
    nested.rollback()
    assert harness.repo.list_intents(limit=10) == ()
    harness.evaluate_at_close("BTC", bundle, eval_time)
    assert len(harness.repo.list_intents(limit=10)) == 1


def test_fill_idempotent_after_simulated_restart(e2e_harness: PaperE2EHarness) -> None:
    harness = e2e_harness
    hist = build_breakout_historical_bundle("BTC")
    bundle, eval_time = historical_to_strategy_bundle(hist, "BTC", daily_count=30)
    harness.evaluate_at_close("BTC", bundle, eval_time)
    fill_candle = candle_at(hist, "BTC", 30)
    ctx = fill_context_for_bundle(bundle, eval_time, fill_candle)
    harness.fill_at_open(process_time=fill_candle.open_time, symbol_contexts={"BTC": ctx})
    counts = harness.counts()
    harness.fill_at_open(process_time=fill_candle.open_time, symbol_contexts={"BTC": ctx})
    after = harness.counts()
    assert after.fills == counts.fills
    assert after.intents == counts.intents
    wallet = harness.repo.get_wallet()
    assert wallet is not None
    assert wallet.cash < Decimal("100000")
