"""Independent accounting verification from canonical fills."""

from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

import pytest
from paper_trading.accounting_verification import verify_accounting_independent
from paper_trading.enums import PaperFillKind, PaperPositionStatus

from tests.paper_trading.conftest import requires_postgres
from tests.paper_trading.e2e.helpers import (
    PaperE2EHarness,
    build_extended_lifecycle_bundle,
    candle_at,
    fill_context_for_bundle,
    historical_to_strategy_bundle,
)
from tests.paper_trading.soak.helpers import run_deterministic_soak

pytestmark = [requires_postgres, pytest.mark.postgres]

INITIAL_CASH = Decimal("100000")


def test_full_cycle_reconstructs_without_audit_events(e2e_harness: PaperE2EHarness) -> None:
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
    stop_candle = candle_at(hist, symbol, 35)
    harness.process_stops(process_time=stop_candle.close_time, daily_candles={symbol: stop_candle})

    assert verify_accounting_independent(harness.repo, initial_cash=INITIAL_CASH) == []
    exit_fills = [
        f for f in harness.repo.list_all_fills() if f.fill_kind == PaperFillKind.EXIT
    ]
    assert len(exit_fills) == 1


def test_manipulated_audit_does_not_change_reconstruction(e2e_harness: PaperE2EHarness) -> None:
    run_deterministic_soak(e2e_harness, days=60, seed=1)
    before = verify_accounting_independent(e2e_harness.repo, initial_cash=INITIAL_CASH)
    closed = next(
        p for p in e2e_harness.repo.list_positions(limit=100)
        if p.status == PaperPositionStatus.CLOSED
    )
    e2e_harness.repo.append_audit_event(
        event_type="POSITION_CLOSED_STOP",
        aggregate_type="paper_position",
        aggregate_id=closed.position_id,
        payload_json={"fill_price": "999999", "exit_reference": "999999"},
    )
    after = verify_accounting_independent(e2e_harness.repo, initial_cash=INITIAL_CASH)
    assert before == after


def test_missing_exit_fill_detected(e2e_harness: PaperE2EHarness) -> None:
    from sqlalchemy import text

    run_deterministic_soak(e2e_harness, days=60, seed=1)
    repo = e2e_harness.repo
    for fill in repo.list_all_fills():
        if fill.fill_kind == PaperFillKind.EXIT:
            repo.session.execute(
                text("DELETE FROM paper_fills WHERE fill_id = :fid"),
                {"fid": fill.fill_id},
            )
    repo.session.flush()
    issues = verify_accounting_independent(repo, initial_cash=INITIAL_CASH)
    assert any("missing canonical EXIT fill" in issue for issue in issues)


def test_duplicate_exit_fill_detected(e2e_harness: PaperE2EHarness) -> None:
    run_deterministic_soak(e2e_harness, days=60, seed=1)
    repo = e2e_harness.repo
    exit_fill = next(f for f in repo.list_all_fills() if f.fill_kind == PaperFillKind.EXIT)
    from paper_trading.db.orm import PaperFillRow

    duplicate = PaperFillRow(
        fill_id=uuid4(),
        paper_order_id=None,
        position_id=exit_fill.position_id,
        fill_kind=PaperFillKind.EXIT.value,
        symbol=exit_fill.symbol,
        side=exit_fill.side.value,
        quantity=exit_fill.quantity,
        market_open_price=exit_fill.market_open_price,
        slippage=exit_fill.slippage,
        fill_price=exit_fill.fill_price,
        fee=exit_fill.fee,
        fill_time=exit_fill.fill_time,
        candle_key=exit_fill.candle_key,
        fill_sequence=1,
        deterministic_fill_key=f"duplicate:{exit_fill.deterministic_fill_key}",
    )
    repo.session.add(duplicate)
    repo.session.flush()
    issues = verify_accounting_independent(repo, initial_cash=INITIAL_CASH)
    assert any("duplicate EXIT fill" in issue for issue in issues)


def test_wrong_exit_fee_detected(e2e_harness: PaperE2EHarness) -> None:
    run_deterministic_soak(e2e_harness, days=60, seed=1)
    repo = e2e_harness.repo
    wallet = repo.get_wallet()
    assert wallet is not None
    repo.update_wallet(fees_delta=Decimal("1"))
    issues = verify_accounting_independent(repo, initial_cash=INITIAL_CASH)
    assert any("fees mismatch" in issue for issue in issues)


def test_wrong_wallet_cash_detected(e2e_harness: PaperE2EHarness) -> None:
    run_deterministic_soak(e2e_harness, days=60, seed=1)
    repo = e2e_harness.repo
    repo.update_wallet(cash_delta=Decimal("100"))
    issues = verify_accounting_independent(repo, initial_cash=INITIAL_CASH)
    assert any("cash mismatch" in issue for issue in issues)


def test_closed_position_has_no_open_exposure(e2e_harness: PaperE2EHarness) -> None:
    run_deterministic_soak(e2e_harness, days=60, seed=1)
    for pos in e2e_harness.repo.list_positions(limit=100):
        if pos.status == PaperPositionStatus.CLOSED:
            assert pos.margin_reserved == 0
            assert pos.quantity > 0


def test_verifier_reports_nonzero_exit_on_wallet_mismatch(e2e_harness: PaperE2EHarness) -> None:
    run_deterministic_soak(e2e_harness, days=30, seed=1)
    e2e_harness.repo.update_wallet(cash_delta=Decimal("50"))
    issues = verify_accounting_independent(e2e_harness.repo, initial_cash=INITIAL_CASH)
    assert issues


def test_nonzero_funding_without_events_detected(e2e_harness: PaperE2EHarness) -> None:
    """AUD-P1-011: unexpected wallet.total_funding must fail independent reconciliation."""
    run_deterministic_soak(e2e_harness, days=30, seed=1)
    repo = e2e_harness.repo
    assert repo.list_funding_events() == []
    repo.update_wallet(funding_delta=Decimal("12.34"))
    issues = verify_accounting_independent(repo, initial_cash=INITIAL_CASH)
    assert any("funding" in issue for issue in issues)
