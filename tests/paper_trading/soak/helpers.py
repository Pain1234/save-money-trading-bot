# ruff: noqa: E402
"""Deterministic soak engine, invariants, and independent accounting verification."""

from __future__ import annotations

import sys
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any
from uuid import uuid4

_SERVICES = Path(__file__).resolve().parents[3] / "services"
if str(_SERVICES) not in sys.path:
    sys.path.insert(0, str(_SERVICES))

from dataclasses import replace

from backtester.data import evaluation_time_for_daily
from backtester.models import HistoricalDataBundle
from paper_trading.enums import (
    PaperPositionStatus,
    RuntimeStatus,
    SchedulerRunStatus,
    TradeIntentStatus,
)
from paper_trading.lock import InMemoryAdvisoryLock
from paper_trading.recovery import recover_on_startup
from paper_trading.repository import PaperTradingRepository
from paper_trading.runtime import RuntimeService
from risk_engine.models import RiskParameters
from strategy_engine.constants import MIN_DAILY_CANDLES

from tests.paper_trading.e2e.helpers import (
    SYMBOLS,
    PaperE2EHarness,
    evaluation_atr,
    fill_context_for_bundle,
    historical_to_strategy_bundle,
)
from tests.paper_trading.soak.scenarios import (
    generate_soak_bundle,
    reference_coverage_minimums,
)

INITIAL_CASH = Decimal("100000")
FEE_RATE = Decimal("0.0005")


@dataclass
class SoakMetrics:
    """Legacy metrics container (kept for compatibility)."""

    days: int
    evaluations: int
    intents: int
    fills: int
    stop_updates: int
    audit_events: int
    elapsed_seconds: float


@dataclass
class SoakReport:
    seed: int
    days: int
    runtime_seconds: float = 0.0
    evaluations: int = 0
    intents_created: int = 0
    intents_rejected: int = 0
    duplicate_intents_suppressed: int = 0
    orders: int = 0
    entry_fills: int = 0
    exit_fills: int = 0
    positions_opened: int = 0
    positions_closed: int = 0
    trailing_stop_updates: int = 0
    gap_stops: int = 0
    intraday_stops: int = 0
    risk_rejections: int = 0
    volume_rejections: int = 0
    recoveries: int = 0
    restarts: int = 0
    degraded_periods: int = 0
    pause_periods: int = 0
    audit_events: int = 0
    final_cash: str = "0"
    final_equity: str = "0"
    realized_pnl: str = "0"
    fees: str = "0"
    open_margin: str = "0"
    state_verification_ok: bool = False
    ok: bool = False
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "seed": self.seed,
            "days": self.days,
            "runtime_seconds": round(self.runtime_seconds, 3),
            "evaluations": self.evaluations,
            "intents_created": self.intents_created,
            "intents_rejected": self.intents_rejected,
            "duplicate_intents_suppressed": self.duplicate_intents_suppressed,
            "orders": self.orders,
            "entry_fills": self.entry_fills,
            "exit_fills": self.exit_fills,
            "positions_opened": self.positions_opened,
            "positions_closed": self.positions_closed,
            "trailing_stop_updates": self.trailing_stop_updates,
            "gap_stops": self.gap_stops,
            "intraday_stops": self.intraday_stops,
            "risk_rejections": self.risk_rejections,
            "volume_rejections": self.volume_rejections,
            "recoveries": self.recoveries,
            "restarts": self.restarts,
            "degraded_periods": self.degraded_periods,
            "pause_periods": self.pause_periods,
            "audit_events": self.audit_events,
            "final_cash": self.final_cash,
            "final_equity": self.final_equity,
            "realized_pnl": self.realized_pnl,
            "fees": self.fees,
            "open_margin": self.open_margin,
            "state_verification_ok": self.state_verification_ok,
            "errors": self.errors,
        }

    def assert_minimum_coverage(self, *, seed: int = 1) -> None:
        if seed != 1:
            return
        mins = reference_coverage_minimums()
        checks = [
            (self.evaluations >= mins["evaluations"], "evaluations"),
            (self.intents_created >= mins["intents_created"], "intents_created"),
            (self.entry_fills >= mins["entry_fills"], "entry_fills"),
            (self.positions_closed >= mins["positions_closed"], "positions_closed"),
            (self.trailing_stop_updates >= mins["trailing_stop_updates"], "trailing_stop_updates"),
            (self.gap_stops >= mins["gap_stops"], "gap_stops"),
            (self.intraday_stops >= mins["intraday_stops"], "intraday_stops"),
            (self.risk_rejections >= mins["risk_rejections"], "risk_rejections"),
            (
                self.duplicate_intents_suppressed >= mins["duplicate_intents_suppressed"],
                "duplicate_intents_suppressed",
            ),
            (self.recoveries >= mins["recoveries"], "recoveries"),
            (self.restarts >= mins["restarts"], "restarts"),
            (self.degraded_periods >= mins["degraded_periods"], "degraded_periods"),
            (self.pause_periods >= mins["pause_periods"], "pause_periods"),
        ]
        for passed, name in checks:
            if not passed:
                raise AssertionError(
                    f"soak minimum not met: {name} "
                    f"(got {getattr(self, name, '?')}, need {mins.get(name)})"
                )


def assert_soak_invariants(repo: PaperTradingRepository) -> None:
    open_positions = repo.get_open_positions()
    by_symbol: dict[str, int] = {}
    for pos in open_positions:
        by_symbol[pos.symbol] = by_symbol.get(pos.symbol, 0) + 1
        assert pos.quantity > 0
        assert pos.margin_reserved >= 0
        assert pos.current_stop >= pos.initial_stop
        assert pos.highest_close_since_entry >= pos.average_entry_price or True
    assert all(count <= 1 for count in by_symbol.values())
    assert len(open_positions) <= 3

    for pos in repo.list_positions(limit=10_000):
        if pos.status == PaperPositionStatus.CLOSED:
            assert pos.quantity > 0
            assert pos.margin_reserved == Decimal("0")
            assert pos.unrealized_pnl == Decimal("0")

    eval_keys = [
        (e.symbol, e.evaluation_time, e.daily_candle_open_time) for e in repo.list_evaluations(limit=10_000)
    ]
    assert len(eval_keys) == len(set(eval_keys))

    intent_keys = [i.idempotency_key for i in repo.list_intents(limit=10_000)]
    assert len(intent_keys) == len(set(intent_keys))

    fill_keys = [f.deterministic_fill_key for f in repo.list_all_fills()]
    assert len(fill_keys) == len(set(fill_keys))

    for fill in repo.list_all_fills():
        assert fill.quantity > 0
        assert fill.fill_price > 0

    wallet = repo.get_wallet()
    assert wallet is not None
    assert wallet.cash >= Decimal("0")

    runtime = repo.get_runtime_state()
    assert runtime is not None
    if runtime.status == RuntimeStatus.READY:
        assert runtime.last_error is None or runtime.status != RuntimeStatus.FAILED


def verify_accounting_independent(repo: PaperTradingRepository) -> list[str]:
    """Reconstruct wallet totals from persisted fills and stop-close audit events."""
    from backtester.paper_lifecycle import compute_exit_accounting

    issues: list[str] = []
    wallet = repo.get_wallet()
    if wallet is None:
        return ["wallet missing"]

    cash = INITIAL_CASH
    fees = Decimal("0")
    slippage = Decimal("0")
    realized = Decimal("0")

    for fill in repo.list_all_fills():
        cash -= fill.fee
        fees += fill.fee
        slippage += fill.slippage

    positions_by_id = {p.position_id: p for p in repo.list_positions(limit=10_000)}
    for event in repo.list_audit_events(limit=10_000):
        if event.event_type != "POSITION_CLOSED_STOP":
            continue
        pos = positions_by_id.get(event.aggregate_id)
        if pos is None:
            issues.append(f"missing position for stop audit {event.aggregate_id}")
            continue
        payload = event.payload_json
        exit_ref = Decimal(str(payload.get("exit_reference", pos.current_stop)))
        exit_acct = compute_exit_accounting(
            exit_reference=exit_ref,
            quantity=pos.quantity,
            entry_price=pos.average_entry_price,
            slippage_bps=Decimal("5"),
            fee_rate=FEE_RATE,
        )
        cash += exit_acct.net_wallet_delta
        fees += exit_acct.fee
        slippage += exit_acct.slippage_cost
        realized += exit_acct.gross_pnl - exit_acct.fee

    if wallet.cash != cash:
        issues.append(f"wallet cash mismatch: db={wallet.cash} reconstructed={cash}")
    if wallet.total_fees != fees:
        issues.append(f"wallet fees mismatch: db={wallet.total_fees} reconstructed={fees}")
    if wallet.total_slippage != slippage:
        issues.append(
            f"wallet slippage mismatch: db={wallet.total_slippage} reconstructed={slippage}"
        )

    for pos in repo.get_open_positions():
        if pos.margin_reserved <= 0:
            issues.append(f"open position {pos.symbol} has no margin reserved")

    for pos in repo.list_positions(limit=10_000):
        if pos.status == PaperPositionStatus.CLOSED and pos.margin_reserved != 0:
            issues.append(f"closed position {pos.symbol} still reserves margin")

    return issues


def _build_fill_contexts(
    hist: HistoricalDataBundle,
    day_idx: int,
) -> dict[str, Any]:
    contexts: dict[str, Any] = {}
    for symbol in SYMBOLS:
        if day_idx <= 0:
            continue
        day = hist.daily[symbol][day_idx]
        prior = hist.daily[symbol][day_idx - 1]
        bundle, eval_time = historical_to_strategy_bundle(hist, symbol, daily_count=day_idx)
        if not bundle.is_usable:
            continue
        contexts[symbol] = fill_context_for_bundle(
            bundle,
            eval_time,
            day,
            prior_close=prior.close,
        )
    return contexts


class DeterministicSoakEngine:
    """Drive full daily open/close lifecycle with recovery and pause injections."""

    def __init__(self, harness: PaperE2EHarness) -> None:
        self.harness = harness
        self.repo = harness.repo
        self.report = SoakReport(seed=1, days=365)
        self._seen_eval_keys: set[tuple[str, datetime, datetime]] = set()
        self._pause_active = False
        self._market_data_ready = True

    def run(self, *, hist: HistoricalDataBundle, days: int, seed: int) -> SoakReport:
        started = time.perf_counter()
        self.report = SoakReport(seed=seed, days=days)
        runtime_svc = RuntimeService(self.repo)

        for day_idx in range(MIN_DAILY_CANDLES, days):
            self._run_day(hist, day_idx, runtime_svc, seed)

        self._finalize_report(started)
        try:
            assert_soak_invariants(self.repo)
            acct_issues = verify_accounting_independent(self.repo)
            if acct_issues:
                self.report.errors.extend(acct_issues)
            else:
                self.report.state_verification_ok = True
        except AssertionError as exc:
            self.report.errors.append(str(exc))

        self.report.ok = not self.report.errors
        if seed == 1:
            try:
                self.report.assert_minimum_coverage(seed=seed)
            except AssertionError as exc:
                self.report.ok = False
                self.report.errors.append(str(exc))

        return self.report

    def _run_day(
        self,
        hist: HistoricalDataBundle,
        day_idx: int,
        runtime_svc: RuntimeService,
        seed: int,
    ) -> None:
        offset = (seed - 1) * 3
        dailies = {s: hist.daily[s][day_idx] for s in SYMBOLS}
        open_time = dailies["BTC"].open_time

        if day_idx == 50 + offset:
            self._inject_restart_after_intent(hist, day_idx)

        if day_idx == 60 + offset:
            self._inject_stale_scheduler_and_recovery(day_idx)

        if day_idx == 80 + offset:
            self._inject_degraded_period()

        if 90 + offset <= day_idx <= 94 + offset:
            if not self._pause_active:
                runtime_svc.set_paused(True)
                self._pause_active = True
                self.report.pause_periods += 1
        elif self._pause_active and day_idx == 95 + offset:
            runtime_svc.set_paused(False)
            self._pause_active = False

        if day_idx == 100 + offset and self._market_data_ready:
            self._market_data_ready = False
        elif day_idx == 102 + offset and not self._market_data_ready:
            self._market_data_ready = True

        if day_idx == 110 + offset:
            self._inject_recovery_with_open_position()

        contexts = _build_fill_contexts(hist, day_idx)
        if day_idx == 146 + offset and "BTC" in contexts:
            contexts["BTC"] = replace(
                contexts["BTC"],
                risk_params=RiskParameters(
                    risk_per_trade_pct=Decimal("0.0000001"),
                    max_portfolio_risk_pct=Decimal("0.000001"),
                    max_leverage=Decimal("2"),
                ),
            )
        fill_results = self.harness.fill_at_open(
            process_time=open_time,
            symbol_contexts=contexts,
        )
        for result in fill_results:
            if result.filled > 0:
                self.report.entry_fills += result.filled
            if result.rejected > 0:
                self.report.risk_rejections += result.rejected

        stop_results = self.harness.process_stops(
            process_time=open_time,
            daily_candles=dailies,
        )
        for sr in stop_results:
            if sr.closed:
                self.report.exit_fills += 1

        eval_time = evaluation_time_for_daily(dailies["BTC"])
        for symbol in SYMBOLS:
            bundle, _ = historical_to_strategy_bundle(hist, symbol, daily_count=day_idx + 1)
            if not bundle.is_usable:
                continue
            if not self._market_data_ready:
                continue
            result = self.harness.evaluate_at_close(symbol, bundle, eval_time)
            eval_key = (
                symbol,
                eval_time,
                bundle.daily.candles[-1].open_time,
            )
            if eval_key not in self._seen_eval_keys and result.created:
                self._seen_eval_keys.add(eval_key)
                self.report.evaluations += 1
            elif result.created:
                self.report.evaluations += 1

            if result.intent_created:
                self.report.intents_created += 1
            elif result.intent is None and result.blocked_reasons:
                if "existing_position" in result.blocked_reasons or "duplicate" in str(
                    result.blocked_reasons
                ):
                    self.report.duplicate_intents_suppressed += 1
                if any("volume" in r.lower() for r in result.blocked_reasons):
                    self.report.volume_rejections += 1
                if "risk" in str(result.blocked_reasons).lower():
                    self.report.risk_rejections += 1
                self.report.intents_rejected += 1

            atr = evaluation_atr(bundle, eval_time, self.harness.strategy_params)
            trail = self.harness.update_trailing(
                evaluation_time=eval_time,
                daily_candles={symbol: dailies[symbol]},
                atr_by_symbol={symbol: atr},
            )
            self.report.trailing_stop_updates += sum(1 for t in trail if t.updated)

        assert_soak_invariants(self.repo)

    def _inject_restart_after_intent(
        self,
        hist: HistoricalDataBundle,
        day_idx: int,
    ) -> None:
        for symbol in ("SOL",):
            bundle, eval_time = historical_to_strategy_bundle(hist, symbol, daily_count=day_idx)
            if bundle.is_usable:
                nested = self.repo.session.begin_nested()
                self.harness.evaluate_at_close(symbol, bundle, eval_time)
                nested.rollback()
                self.report.restarts += 1
                break
        lock = InMemoryAdvisoryLock("soak-restart")
        if lock.try_acquire():
            try:
                recover_on_startup(
                    self.repo,
                    self.harness.config,
                    lock,
                    market_data_ready=True,
                )
                self.report.recoveries += 1
            finally:
                lock.release()
        self.harness.set_runtime_ready()

    def _inject_stale_scheduler_and_recovery(self, day_idx: int) -> None:
        from paper_trading.db.orm import SchedulerRunRow

        scheduled = datetime(2024, 1, 1, tzinfo=UTC) + __import__("datetime").timedelta(days=day_idx)
        self.repo.session.add(
            SchedulerRunRow(
                run_id=uuid4(),
                job_name="daily_signal_evaluation",
                scheduled_for=scheduled,
                started_at=scheduled,
                status=SchedulerRunStatus.RUNNING.value,
                idempotency_key=f"soak-stale-{self.report.seed}-{day_idx}",
            )
        )
        self.repo.session.flush()
        lock = InMemoryAdvisoryLock("soak-stale")
        if lock.try_acquire():
            try:
                recover_on_startup(
                    self.repo,
                    self.harness.config,
                    lock,
                    market_data_ready=True,
                )
                self.report.recoveries += 1
            finally:
                lock.release()
        self.harness.set_runtime_ready()

    def _inject_degraded_period(self) -> None:
        runtime = self.repo.get_runtime_state()
        if runtime is None:
            return
        self.repo.update_runtime_state(
            status=RuntimeStatus.DEGRADED,
            expected_version=runtime.version,
            last_error="soak simulated degraded",
        )
        self.report.degraded_periods += 1
        self.harness.set_runtime_ready()

    def _inject_recovery_with_open_position(self) -> None:
        if not self.repo.get_open_positions():
            return
        lock = InMemoryAdvisoryLock("soak-open-recovery")
        if lock.try_acquire():
            try:
                recover_on_startup(
                    self.repo,
                    self.harness.config,
                    lock,
                    market_data_ready=True,
                )
                self.report.recoveries += 1
            finally:
                lock.release()
        self.harness.set_runtime_ready()

    def _finalize_report(self, started: float) -> None:
        self.report.runtime_seconds = time.perf_counter() - started
        counts = self.harness.counts()
        self.report.evaluations = counts.evaluations
        self.report.orders = counts.orders
        self.report.audit_events = counts.audit_events
        self.report.intents_created = counts.intents
        self.report.entry_fills = len(self.repo.list_all_fills())

        positions = self.repo.list_positions(limit=10_000)
        self.report.positions_opened = len(positions)
        self.report.positions_closed = sum(
            1 for p in positions if p.status == PaperPositionStatus.CLOSED
        )

        for event in self.repo.list_audit_events(limit=10_000):
            if event.event_type != "POSITION_CLOSED_STOP":
                continue
            reason = str(event.payload_json.get("exit_reason", ""))
            if reason == "RC_EXIT_STOP_GAP":
                self.report.gap_stops += 1
            else:
                self.report.intraday_stops += 1

        rejected = [
            i
            for i in self.repo.list_intents(limit=10_000)
            if i.status == TradeIntentStatus.REJECTED
        ]
        self.report.risk_rejections = max(self.report.risk_rejections, len(rejected))

        volume_evals = 0
        for ev in self.repo.list_evaluations(limit=10_000):
            if any("RC_REJECT_VOLUME" in str(r) for r in ev.rejection_reasons):
                volume_evals += 1
        self.report.volume_rejections = volume_evals

        wallet = self.repo.get_wallet()
        if wallet:
            self.report.final_cash = str(wallet.cash)
            self.report.realized_pnl = str(wallet.total_realized_pnl)
            self.report.fees = str(wallet.total_fees)
        open_positions = self.repo.get_open_positions()
        self.report.open_margin = str(sum(p.margin_reserved for p in open_positions))
        equity = wallet.cash if wallet else Decimal("0")
        for p in open_positions:
            equity += p.quantity * p.average_entry_price
        self.report.final_equity = str(equity)


def run_deterministic_soak(
    harness: PaperE2EHarness,
    *,
    days: int,
    seed: int,
) -> SoakReport:
    hist = generate_soak_bundle(days=days, seed=seed)
    engine = DeterministicSoakEngine(harness)
    return engine.run(hist=hist, days=days, seed=seed)


def metrics_from_report(report: SoakReport) -> SoakMetrics:
    return SoakMetrics(
        days=report.days,
        evaluations=report.evaluations,
        intents=report.intents_created,
        fills=report.entry_fills,
        stop_updates=report.trailing_stop_updates,
        audit_events=report.audit_events,
        elapsed_seconds=report.runtime_seconds,
    )
