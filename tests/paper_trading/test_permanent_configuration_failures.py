"""Regression tests for permanent configuration failures (OLR-003/OLR-004)."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest
from market_data.models import MarketSymbol, MarketTimeframe, NormalizedCandle
from market_data.repository import InMemoryCandleRepository
from market_data.timeframes import daily_close
from paper_trading.clock import FixedClock
from paper_trading.constraint_validation import validate_production_symbol_constraints
from paper_trading.db.orm import SchedulerRunRow
from paper_trading.enums import RuntimeStatus, SchedulerRunStatus
from paper_trading.event_fairness import MarketEventGroupState
from paper_trading.market_event_errors import (
    PERMANENT_CONFIGURATION_FAILURE,
    PERMANENT_CONFIGURATION_INVALID_QUANTITY_STEP,
    PERMANENT_CONFIGURATION_INVALID_TICK_SIZE,
    PermanentConfigurationFailure,
)
from paper_trading.market_events import (
    MarketEventBridge,
    MarketEventDetector,
)
from paper_trading.models import SchedulerRun
from paper_trading.readiness import ReadinessService
from paper_trading.scheduler import JobRunOutcome
from paper_trading.scheduler_context import ProductionContextBuilder
from paper_trading.symbol_constraints import StaticSymbolConstraintsProvider
from risk_engine.models import SymbolConstraints

from tests.paper_trading.bridge_test_helpers import poll_commit_ack
from tests.paper_trading.conftest_execution import DEFAULT_CONSTRAINTS, utc_dt


def _daily(symbol: str, open_time: datetime, *, is_closed: bool = False) -> NormalizedCandle:
    return NormalizedCandle(
        symbol=MarketSymbol(symbol),
        timeframe=MarketTimeframe.DAILY,
        open_time=open_time,
        close_time=daily_close(open_time),
        open=Decimal("100"),
        high=Decimal("105"),
        low=Decimal("95"),
        close=Decimal("100"),
        volume=Decimal("1000"),
        is_closed=is_closed,
    )


def _valid_constraints(**overrides: Decimal) -> SymbolConstraints:
    data = DEFAULT_CONSTRAINTS.model_dump()
    data.update(overrides)
    return SymbolConstraints.model_validate(data)


def _repo_with_permanent_tracking() -> MagicMock:
    repo = MagicMock()
    runs: dict[tuple[str, datetime], SchedulerRunRow] = {}
    errors: dict[tuple[str, datetime], str | None] = {}
    statuses: dict[tuple[str, datetime], str] = {}

    def get_run(job_name: str, scheduled_for: datetime) -> SchedulerRun | None:
        row = runs.get((job_name, scheduled_for))
        if row is None:
            return None
        key = (job_name, scheduled_for)
        return SchedulerRun(
            run_id=row.run_id,
            job_name=row.job_name,
            scheduled_for=row.scheduled_for,
            started_at=row.started_at,
            completed_at=row.started_at,
            status=SchedulerRunStatus(statuses.get(key, row.status)),
            error=errors.get(key),
            idempotency_key=row.idempotency_key,
            recovery_of_run_id=getattr(row, "recovery_of_run_id", None),
            resolved_by_run_id=getattr(row, "resolved_by_run_id", None),
        )

    def insert_or_get(job_row: SchedulerRunRow) -> tuple[SchedulerRunRow, bool]:
        key = (job_row.job_name, job_row.scheduled_for)
        if key in runs:
            return runs[key], False
        runs[key] = job_row
        statuses[key] = job_row.status
        return job_row, True

    def complete_run(
        *,
        job_name: str,
        scheduled_for: datetime,
        status: SchedulerRunStatus,
        completed_at: datetime,
        error: str | None,
    ) -> None:
        key = (job_name, scheduled_for)
        row = runs.get(key)
        if row is not None:
            row.status = status.value
            statuses[key] = status.value
            errors[key] = error

    def list_permanent_configuration_failures() -> tuple[SchedulerRun, ...]:
        from paper_trading.market_event_errors import PERMANENT_CONFIGURATION_ERROR_CODES

        result: list[SchedulerRun] = []
        for (job_name, scheduled_for), row in runs.items():
            if not job_name.startswith("me:"):
                continue
            if ":recovery:" in job_name:
                continue
            if getattr(row, "resolved_by_run_id", None) is not None:
                continue
            error = errors.get((job_name, scheduled_for))
            status = statuses.get((job_name, scheduled_for), row.status)
            if status != SchedulerRunStatus.FAILED.value:
                continue
            if error not in PERMANENT_CONFIGURATION_ERROR_CODES:
                continue
            run = get_run(job_name, scheduled_for)
            if run is not None:
                result.append(run)
        return tuple(result)

    def create_recovery_attempt(
        *,
        original_run: SchedulerRun,
        recovery_job_name: str,
        started_at: datetime,
    ) -> tuple[SchedulerRun, bool]:
        key = (recovery_job_name, original_run.scheduled_for)
        if key in runs:
            run = get_run(recovery_job_name, original_run.scheduled_for)
            assert run is not None
            return run, False
        row = SchedulerRunRow(
            run_id=__import__("uuid").uuid4(),
            job_name=recovery_job_name,
            scheduled_for=original_run.scheduled_for,
            started_at=started_at,
            status=SchedulerRunStatus.RUNNING.value,
            idempotency_key=f"{recovery_job_name}:recovery",
            recovery_of_run_id=original_run.run_id,
        )
        runs[key] = row
        statuses[key] = row.status
        run = get_run(recovery_job_name, original_run.scheduled_for)
        assert run is not None
        return run, True

    def count_recovery_attempts(original_run_id) -> int:
        return sum(
            1
            for (job_name, _scheduled_for), row in runs.items()
            if getattr(row, "recovery_of_run_id", None) == original_run_id
            or (
                job_name.startswith("me:")
                and ":recovery:" in job_name
            )
        )

    def get_active_recovery_attempt(original_run_id):
        for (job_name, scheduled_for), row in runs.items():
            if ":recovery:" not in job_name:
                continue
            if statuses.get((job_name, scheduled_for), row.status) != SchedulerRunStatus.RUNNING.value:
                continue
            return get_run(job_name, scheduled_for)
        return None

    def mark_run_resolved(*, original_run_id, recovery_run_id) -> None:
        for _key, row in runs.items():
            if row.run_id == original_run_id:
                row.resolved_by_run_id = recovery_run_id

    repo.get_scheduler_run.side_effect = get_run
    repo.insert_or_get_scheduler_run.side_effect = insert_or_get
    repo.complete_scheduler_run.side_effect = complete_run
    repo.list_permanent_configuration_failures.side_effect = list_permanent_configuration_failures
    repo.create_recovery_attempt.side_effect = create_recovery_attempt
    repo.count_recovery_attempts.side_effect = count_recovery_attempts
    repo.get_active_recovery_attempt.side_effect = get_active_recovery_attempt
    repo.mark_run_resolved.side_effect = mark_run_resolved
    repo.delete_scheduler_run_if_running.return_value = False
    repo.get_running_scheduler_runs.return_value = ()
    fairness_cursor = {"value": 0}
    group_states: dict[str, MarketEventGroupState] = {}
    repo.get_fairness_group_rotation_cursor.side_effect = lambda: fairness_cursor["value"]
    repo.set_fairness_group_rotation_cursor.side_effect = (
        lambda *, cursor, updated_at: fairness_cursor.update(value=cursor)
    )
    repo.list_market_event_group_states.side_effect = lambda: dict(group_states)
    repo.delete_market_event_group_state.side_effect = lambda group_key: group_states.pop(
        group_key, None
    )

    def upsert_group_deferred(
        *,
        group_key: str,
        event_type: str,
        group_time: datetime,
        next_attempt_at: datetime,
        defer_count: int,
        updated_at: datetime,
    ) -> None:
        group_states[group_key] = MarketEventGroupState(
            group_key=group_key,
            event_type=event_type,
            group_time=group_time,
            next_attempt_at=next_attempt_at,
            defer_count=defer_count,
        )

    repo.upsert_market_event_group_deferred.side_effect = upsert_group_deferred
    return repo


def _open_subjob_outcome() -> JobRunOutcome:
    return JobRunOutcome(
        job_name="subjob",
        scheduled_for=utc_dt(2024, 1, 16),
        status=SchedulerRunStatus.COMPLETED,
        skipped=False,
    )


def _build_bridge(
    *,
    repo: MagicMock,
    candle_repo: InMemoryCandleRepository,
    context_builder: ProductionContextBuilder | MagicMock,
    symbols: tuple[str, ...] = ("BTC",),
    max_events_per_poll: int = 256,
) -> MarketEventBridge:
    eval_time = utc_dt(2024, 1, 16, 1)
    scheduler = MagicMock()
    scheduler.run_daily_open_gap_stop.return_value = (_open_subjob_outcome(),)
    scheduler.run_daily_open_fill.return_value = (_open_subjob_outcome(),)
    scheduler.run_daily_open_snapshot.return_value = (_open_subjob_outcome(),)
    advisory_lock = MagicMock()
    advisory_lock.held = True
    config = MagicMock(
        symbols=symbols,
        evaluation_delay_seconds=5,
        fill_delay_seconds=0,
    )
    return MarketEventBridge(
        repository=repo,
        candle_repository=candle_repo,
        scheduler=scheduler,
        context_builder=context_builder,
        config=config,
        clock=FixedClock(eval_time),
        advisory_lock=advisory_lock,
        market_data_ready=lambda: True,
        detector=MarketEventDetector(symbols=symbols, evaluation_delay_seconds=5),
        max_events_per_poll=max_events_per_poll,
    )


def _readiness_config() -> MagicMock:
    config = MagicMock()
    config.stale_runtime_threshold_seconds = 7200
    config.scheduler_enabled = False
    return config


def _evaluate_readiness(repo: MagicMock, eval_time: datetime):
    readiness = ReadinessService(repo, _readiness_config(), clock=FixedClock(eval_time))
    runtime = MagicMock()
    runtime.status = RuntimeStatus.READY
    runtime.paused = False
    runtime.kill_switch = False
    runtime.last_error = ""
    runtime.heartbeat_at = eval_time
    repo.get_runtime_state.return_value = runtime
    return readiness.evaluate(market_data_ready=True, scheduler_active=True)


def _context_builder(constraints: dict[str, SymbolConstraints]) -> ProductionContextBuilder:
    repo = MagicMock()
    runtime = MagicMock()
    runtime.status = RuntimeStatus.READY
    runtime.kill_switch = False
    runtime.paused = False
    repo.get_runtime_state.return_value = runtime

    bundle = MagicMock()
    bundle.is_usable = True
    bundle.daily.candles = [MagicMock()]
    market_data = MagicMock()
    market_data.build_strategy_bundle.return_value = bundle
    market_data.repository.get_closed_before.return_value = []

    config = MagicMock()
    config.symbols = tuple(constraints.keys()) or ("BTC",)
    config.paper_max_leverage = Decimal("2")

    from paper_trading.models import PaperExecutionConfig
    from risk_engine.models import RiskParameters

    return ProductionContextBuilder(
        market_data=market_data,
        repository=repo,
        config=config,
        constraints=StaticSymbolConstraintsProvider(constraints),
        clock=FixedClock(utc_dt(2024, 1, 16, 1)),
        execution_config=PaperExecutionConfig(
            fee_rate=Decimal("0.0005"),
            slippage_bps=Decimal("5"),
            max_leverage=Decimal("2"),
        ),
        risk_params=RiskParameters(
            risk_per_trade_pct=Decimal("0.005"),
            max_portfolio_risk_pct=Decimal("0.02"),
            max_leverage=Decimal("2"),
        ),
        market_data_ready=lambda: True,
    )


def _patch_strategy_engine_success():
    eval_result = MagicMock()
    eval_result.atr = Decimal("2")
    return patch(
        "strategy_engine.engine.StrategyEngine.evaluate",
        return_value=eval_result,
    )


@pytest.mark.parametrize(
    ("tick_size", "expected_code"),
    [
        (Decimal("0"), PERMANENT_CONFIGURATION_INVALID_TICK_SIZE),
        (Decimal("-0.01"), PERMANENT_CONFIGURATION_INVALID_TICK_SIZE),
    ],
)
def test_invalid_tick_size_rejected(tick_size: Decimal, expected_code: str) -> None:
    constraints = _valid_constraints(price_tick_size=tick_size)
    with pytest.raises(PermanentConfigurationFailure) as exc:
        validate_production_symbol_constraints(symbol="BTC", constraints=constraints)
    assert exc.value.code == expected_code


@pytest.mark.parametrize(
    "tick_size",
    [Decimal("NaN"), Decimal("Infinity")],
)
def test_non_finite_tick_size_rejected(tick_size: Decimal) -> None:
    constraints = SymbolConstraints.model_construct(
        quantity_step=Decimal("0.001"),
        minimum_quantity=Decimal("0.001"),
        minimum_notional=Decimal("10"),
        price_tick_size=tick_size,
    )
    with pytest.raises(PermanentConfigurationFailure) as exc:
        validate_production_symbol_constraints(symbol="BTC", constraints=constraints)
    assert exc.value.code == PERMANENT_CONFIGURATION_INVALID_TICK_SIZE


@pytest.mark.parametrize(
    ("quantity_step", "expected_code"),
    [
        (Decimal("0"), PERMANENT_CONFIGURATION_INVALID_QUANTITY_STEP),
        (Decimal("-0.001"), PERMANENT_CONFIGURATION_INVALID_QUANTITY_STEP),
    ],
)
def test_invalid_quantity_step_rejected(
    quantity_step: Decimal,
    expected_code: str,
) -> None:
    constraints = SymbolConstraints(
        quantity_step=quantity_step,
        minimum_quantity=Decimal("0.001"),
        minimum_notional=Decimal("10"),
        price_tick_size=Decimal("0.01"),
    )
    with pytest.raises(PermanentConfigurationFailure) as exc:
        validate_production_symbol_constraints(symbol="BTC", constraints=constraints)
    assert exc.value.code == expected_code


@pytest.mark.parametrize(
    "quantity_step",
    [Decimal("NaN"), Decimal("Infinity")],
)
def test_non_finite_quantity_step_rejected(quantity_step: Decimal) -> None:
    constraints = SymbolConstraints.model_construct(
        quantity_step=quantity_step,
        minimum_quantity=Decimal("0.001"),
        minimum_notional=Decimal("10"),
        price_tick_size=Decimal("0.01"),
    )
    with pytest.raises(PermanentConfigurationFailure) as exc:
        validate_production_symbol_constraints(symbol="BTC", constraints=constraints)
    assert exc.value.code == PERMANENT_CONFIGURATION_INVALID_QUANTITY_STEP


def test_missing_constraints_terminal_failed_no_retry_flood() -> None:
    open_time = utc_dt(2024, 1, 16)
    eval_time = utc_dt(2024, 1, 16, 1)
    candle_repo = InMemoryCandleRepository()
    candle_repo.upsert(_daily("BTC", open_time, is_closed=False))

    context_builder = MagicMock(spec=ProductionContextBuilder)
    context_builder.build_open_contexts.side_effect = PermanentConfigurationFailure(
        "missing symbol constraints for BTC",
        error_code=PERMANENT_CONFIGURATION_FAILURE,
    )
    context_builder.validate_symbol_configuration.side_effect = PermanentConfigurationFailure(
        "missing symbol constraints for BTC",
        error_code=PERMANENT_CONFIGURATION_FAILURE,
    )

    repo = _repo_with_permanent_tracking()
    bridge = _build_bridge(repo=repo, candle_repo=candle_repo, context_builder=context_builder)

    first = poll_commit_ack(bridge, repo, eval_time)
    assert first.outcomes[0].status == SchedulerRunStatus.FAILED
    assert first.outcomes[0].error == PERMANENT_CONFIGURATION_FAILURE
    assert first.outcomes[0].terminal_failed is True
    assert len(first.events_terminal_failed) == 1
    assert bridge.detector._trackers["BTC"].daily_open_terminal_failed_time == open_time  # noqa: SLF001
    assert context_builder.build_open_contexts.call_count == 1

    for _ in range(2):
        retry = bridge.process_after_poll(eval_time)
        assert len(retry.outcomes) == 0

    assert context_builder.build_open_contexts.call_count == 1
    assert bridge.has_permanent_failures is True

    snap = _evaluate_readiness(repo, eval_time)
    assert snap.entry_readiness is False
    assert "permanent_configuration_failure" in snap.reasons


def test_configuration_recovery_allows_single_retry() -> None:
    open_time = utc_dt(2024, 1, 16)
    eval_time = utc_dt(2024, 1, 16, 1)
    candle_repo = InMemoryCandleRepository()
    candle_repo.upsert(_daily("BTC", open_time, is_closed=False))

    invalid = _valid_constraints(price_tick_size=Decimal("0"))
    valid = _valid_constraints()
    context_builder = _context_builder({"BTC": invalid})

    repo = _repo_with_permanent_tracking()
    bridge = _build_bridge(repo=repo, candle_repo=candle_repo, context_builder=context_builder)

    first = poll_commit_ack(bridge, repo, eval_time)
    assert first.outcomes[0].status == SchedulerRunStatus.FAILED
    assert first.outcomes[0].error == PERMANENT_CONFIGURATION_INVALID_TICK_SIZE

    context_builder._constraints = StaticSymbolConstraintsProvider({"BTC": valid})  # noqa: SLF001
    event = first.outcomes[0].event
    bridge.recover_permanent_configuration(event)

    with _patch_strategy_engine_success():
        second = poll_commit_ack(bridge, repo, eval_time)
    assert second.outcomes[0].status == SchedulerRunStatus.COMPLETED
    assert bridge.has_permanent_failures is False

    snap = _evaluate_readiness(repo, eval_time)
    assert snap.entry_readiness is True


def test_permanent_failure_does_not_block_later_valid_symbol() -> None:
    open_time = utc_dt(2024, 1, 16)
    eval_time = utc_dt(2024, 1, 16, 1)
    candle_repo = InMemoryCandleRepository()
    candle_repo.upsert(_daily("BTC", open_time, is_closed=False))
    candle_repo.upsert(_daily("ETH", open_time, is_closed=False))

    invalid = _valid_constraints(price_tick_size=Decimal("0"))
    valid = _valid_constraints()
    context_builder = _context_builder({"BTC": invalid, "ETH": valid})

    repo = _repo_with_permanent_tracking()
    bridge = _build_bridge(
        repo=repo,
        candle_repo=candle_repo,
        context_builder=context_builder,
        symbols=("BTC", "ETH"),
    )

    with _patch_strategy_engine_success():
        result = poll_commit_ack(bridge, repo, eval_time)

    btc = next(o for o in result.outcomes if o.event.symbol == "BTC")
    eth = next(o for o in result.outcomes if o.event.symbol == "ETH")
    assert btc.status == SchedulerRunStatus.FAILED
    assert eth.status == SchedulerRunStatus.COMPLETED


def test_context_builder_rejects_invalid_constraints_before_risk() -> None:
    builder = _context_builder({"BTC": _valid_constraints(price_tick_size=Decimal("0"))})
    open_candle = _daily("BTC", utc_dt(2024, 1, 16), is_closed=False)
    with pytest.raises(PermanentConfigurationFailure) as exc:
        builder.build_open_contexts("BTC", open_candle, utc_dt(2024, 1, 16, 1))
    assert exc.value.code == PERMANENT_CONFIGURATION_INVALID_TICK_SIZE
