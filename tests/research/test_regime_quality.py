"""Tests for regime quality metrics (#287)."""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path

import pytest
from backtester.models import BacktestTrade, EntryType, ExitReason
from research.regime import classify_closes, get_classifier
from research.regime_quality import (
    NOT_AVAILABLE,
    RegimeQualityError,
    evaluate_regime_quality,
    evaluate_regime_quality_from_run_dir,
    get_score_policy,
    summarize_slice_score,
    verify_regime_metrics_seal,
    write_regime_metrics_artifact,
)
from research.regime_quality.metrics import (
    compute_slice_metrics,
    max_drawdown_from_episodes,
)
from strategy_engine.models import ReasonCode


def _month_closes(
    *,
    year: int,
    month: int,
    start: Decimal,
    daily_return: Decimal,
    days: int = 20,
) -> list[tuple[date, Decimal]]:
    closes: list[tuple[date, Decimal]] = []
    price = start
    for day in range(1, days + 1):
        closes.append((date(year, month, day), price))
        price = price * (Decimal("1") + daily_return)
    return closes


def _labels_two_regimes() -> dict:
    closes = [
        *_month_closes(
            year=2024, month=1, start=Decimal("100"), daily_return=Decimal("0.006")
        ),
        *_month_closes(
            year=2024, month=2, start=Decimal("100"), daily_return=Decimal("-0.006")
        ),
    ]
    return classify_closes(
        classifier=get_classifier("1.0"),
        closes=closes,
        dataset_id="ds",
        dataset_content_hash="a" * 64,
        reference_symbol="BTC",
    ).artifact


def _labels_three_months() -> dict:
    """Jan BULL, Feb BEAR, Mar BULL — for episode drawdown tests."""
    closes = [
        *_month_closes(
            year=2024, month=1, start=Decimal("100"), daily_return=Decimal("0.006")
        ),
        *_month_closes(
            year=2024, month=2, start=Decimal("100"), daily_return=Decimal("-0.006")
        ),
        *_month_closes(
            year=2024, month=3, start=Decimal("100"), daily_return=Decimal("0.006")
        ),
    ]
    return classify_closes(
        classifier=get_classifier("1.0"),
        closes=closes,
        dataset_id="ds",
        dataset_content_hash="a" * 64,
        reference_symbol="BTC",
    ).artifact


def test_zero_activity_regime_is_valid_not_error() -> None:
    slice_raw = compute_slice_metrics(
        cell_id="SIDEWAYS|LOW_VOL",
        trades=[],
        equity=[],
    )
    assert slice_raw.zero_activity is True
    assert slice_raw.status == "ZERO_ACTIVITY"
    assert slice_raw.closed_trades == 0
    assert slice_raw.net_pnl == Decimal("0")
    summary = summarize_slice_score(slice_raw, policy=get_score_policy("1.0"))
    assert summary["score"] == NOT_AVAILABLE
    assert summary["decision_binding"] is False


def test_gross_net_and_costs_separated() -> None:
    trades = [
        {
            "symbol": "BTC",
            "exit_time": "2024-01-10T00:00:00+00:00",
            "net_pnl": "90",
            "fees": "5",
            "slippage_cost": "3",
            "funding": "2",
            "quantity": "1",
            "entry_fill_price": "100",
        }
    ]
    equity = [
        {
            "time": "2024-01-10T00:00:00+00:00",
            "equity": "1090",
            "open_positions": 1,
        },
        {
            "time": "2024-01-11T00:00:00+00:00",
            "equity": "1100",
            "open_positions": 0,
        },
    ]
    labels = _labels_two_regimes()
    result = evaluate_regime_quality(
        regime_labels=labels,
        trades=trades,
        equity=equity,
        run_id="run_test",
        experiment_id="exp_test",
        dataset_id="ds",
        dataset_content_hash="a" * 64,
    )
    bull = next(r for r in result.artifact["regimes"] if r["trend"] == "BULL")
    assert Decimal(bull["net_pnl"]) == Decimal("90")
    assert Decimal(bull["gross_pnl"]) == Decimal("100")
    assert Decimal(bull["costs"]["fees"]) == Decimal("5")
    assert Decimal(bull["turnover"]) == Decimal("100")
    assert result.artifact["evidence_status"] == "OK"
    assert result.artifact["reconciliation"]["balanced"] is True


def test_unlabeled_trade_preserved_in_reconciliation() -> None:
    labels = _labels_two_regimes()
    trades = [
        {
            "symbol": "BTC",
            "exit_time": "2024-01-15T00:00:00+00:00",
            "net_pnl": "10",
            "fees": "0",
            "slippage_cost": "0",
            "funding": "0",
        },
        {
            "symbol": "BTC",
            # June is outside labeled Jan/Feb series → unlabeled
            "exit_time": "2024-06-15T00:00:00+00:00",
            "net_pnl": "-100",
            "fees": "0",
            "slippage_cost": "0",
            "funding": "0",
        },
    ]
    result = evaluate_regime_quality(
        regime_labels=labels,
        trades=trades,
        equity=[],
        run_id="run_cov",
        experiment_id="exp_cov",
    )
    art = result.artifact
    assert art["coverage"]["closed_trades_total"] == 2
    assert art["coverage"]["closed_trades_labeled"] == 1
    assert art["coverage"]["closed_trades_unlabeled"] == 1
    assert Decimal(art["reconciliation"]["source_net_pnl"]) == Decimal("-90")
    assert Decimal(art["reconciliation"]["excluded_net_pnl"]) == Decimal("-100")
    assert Decimal(art["portfolio"]["net_pnl_source"]) == Decimal("-90")
    assert Decimal(art["portfolio"]["net_pnl_attributed"]) == Decimal("10")
    assert art["evidence_status"] == "INCONCLUSIVE"
    assert art["worst_regime"]["reason"] == "inconclusive_coverage"


def test_drawdown_does_not_import_other_regime_losses() -> None:
    labels = _labels_three_months()
    # Timeline: BULL Jan at 1000, BEAR Feb crash to 500, BULL Mar stays ~500.
    timeline = [
        (date(2024, 1, 10), "BULL|NORMAL_VOL", {"time": "2024-01-10", "equity": "1000"}),
        (date(2024, 1, 20), "BULL|NORMAL_VOL", {"time": "2024-01-20", "equity": "1000"}),
        (date(2024, 2, 10), "BEAR|NORMAL_VOL", {"time": "2024-02-10", "equity": "500"}),
        (date(2024, 2, 20), "BEAR|NORMAL_VOL", {"time": "2024-02-20", "equity": "500"}),
        (date(2024, 3, 10), "BULL|NORMAL_VOL", {"time": "2024-03-10", "equity": "500"}),
        (date(2024, 3, 20), "BULL|NORMAL_VOL", {"time": "2024-03-20", "equity": "510"}),
    ]
    # Force cell ids from actual labels
    bull_cells = {
        f"{p['trend']}|{p['vol']}"
        for p in labels["period_labels"]
        if p["trend"] == "BULL"
    }
    assert len(bull_cells) == 1
    bull_cell = next(iter(bull_cells))
    # Retag timeline with real cell ids from labels
    from research.regime_quality.join import index_day_labels

    idx = index_day_labels(labels)
    tagged = []
    equity_rows = []
    for day, _old, snap in timeline:
        key = idx[day]
        cell = key.cell_id if key.status == "OK" else None
        tagged.append((day, cell, snap))
        equity_rows.append({**snap, "time": f"{day.isoformat()}T00:00:00+00:00"})
    dd = max_drawdown_from_episodes(tagged, bull_cell)
    assert dd is not None
    assert dd < Decimal("0.1")  # must NOT be ~50% from BEAR crash

    result = evaluate_regime_quality(
        regime_labels=labels,
        trades=[],
        equity=equity_rows,
        run_id="run_dd",
        experiment_id="exp_dd",
    )
    bull = next(r for r in result.artifact["regimes"] if r["trend"] == "BULL")
    assert bull["max_drawdown"] != NOT_AVAILABLE
    assert Decimal(bull["max_drawdown"]) < Decimal("0.1")


def test_dataset_pin_mismatch_rejected() -> None:
    labels = _labels_two_regimes()
    with pytest.raises(RegimeQualityError, match="dataset_id pin mismatch"):
        evaluate_regime_quality(
            regime_labels=labels,
            trades=[],
            equity=[],
            run_id="run_pin",
            experiment_id="exp_pin",
            dataset_id="ds-b",
            dataset_content_hash="a" * 64,
        )


def test_from_run_dir_requires_checksums(tmp_path: Path) -> None:
    labels = _labels_two_regimes()
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    (run_dir / "regime_labels.json").write_text(
        __import__("json").dumps(labels), encoding="utf-8"
    )
    (run_dir / "trades.json").write_text("[]", encoding="utf-8")
    (run_dir / "equity.json").write_text("[]", encoding="utf-8")
    (run_dir / "run_manifest.json").write_text(
        __import__("json").dumps(
            {
                "run_id": "run_1",
                "experiment_id": "exp_1",
                "dataset_id": "ds",
                "dataset_content_hash": "a" * 64,
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(RegimeQualityError, match="checksums.json missing"):
        evaluate_regime_quality_from_run_dir(run_dir)


def test_turnover_from_backtest_trade_dump() -> None:
    trade = BacktestTrade(
        symbol="BTC",
        client_intent_id="c1",
        strategy_version="v1",
        entry_type=EntryType.BREAKOUT,
        strategy_reason_codes=(ReasonCode.RC_ENTRY_BREAKOUT_20D,),
        risk_reason_codes=(ReasonCode.RC_RISK_APPROVED,),
        signal_time=datetime(2024, 1, 5, tzinfo=UTC),
        order_time=datetime(2024, 1, 5, tzinfo=UTC),
        entry_time=datetime(2024, 1, 5, tzinfo=UTC),
        entry_reference_price=Decimal("100"),
        entry_fill_price=Decimal("100"),
        quantity=Decimal("2"),
        initial_stop=Decimal("90"),
        exit_time=datetime(2024, 1, 15, tzinfo=UTC),
        exit_reason=ExitReason.END_OF_BACKTEST,
        exit_reference_price=Decimal("110"),
        exit_fill_price=Decimal("110"),
        gross_pnl=Decimal("20"),
        fees=Decimal("1"),
        funding=Decimal("0"),
        slippage_cost=Decimal("0"),
        net_pnl=Decimal("19"),
    )
    payload = __import__("json").loads(trade.model_dump_json())
    labels = _labels_two_regimes()
    result = evaluate_regime_quality(
        regime_labels=labels,
        trades=[payload],
        equity=[],
        run_id="run_t",
        experiment_id="exp_t",
    )
    bull = next(r for r in result.artifact["regimes"] if r["trend"] == "BULL")
    assert Decimal(bull["turnover"]) == Decimal("200")


def test_benchmark_delta_when_closes_provided() -> None:
    labels = _labels_two_regimes()
    closes = {
        date(2024, 1, 1): Decimal("100"),
        date(2024, 1, 20): Decimal("110"),
    }
    equity = [
        {"time": "2024-01-01T00:00:00+00:00", "equity": "1000", "open_positions": 0},
        {"time": "2024-01-20T00:00:00+00:00", "equity": "1050", "open_positions": 0},
    ]
    trades = [
        {
            "symbol": "BTC",
            "exit_time": "2024-01-15T00:00:00+00:00",
            "net_pnl": "50",
            "fees": "0",
            "slippage_cost": "0",
            "funding": "0",
        }
    ]
    result = evaluate_regime_quality(
        regime_labels=labels,
        trades=trades,
        equity=equity,
        run_id="run_bm",
        experiment_id="exp_bm",
        benchmark_closes=closes,
    )
    bull = next(r for r in result.artifact["regimes"] if r["trend"] == "BULL")
    assert bull["benchmark_delta"] != NOT_AVAILABLE


def test_worst_and_strongest_profile() -> None:
    labels = _labels_two_regimes()
    trades = [
        {
            "symbol": "BTC",
            "exit_time": "2024-01-15T12:00:00+00:00",
            "net_pnl": "50",
            "fees": "1",
            "slippage_cost": "0",
            "funding": "0",
        },
        {
            "symbol": "BTC",
            "exit_time": "2024-02-15T12:00:00+00:00",
            "net_pnl": "-80",
            "fees": "1",
            "slippage_cost": "0",
            "funding": "0",
        },
    ]
    equity = [
        {"time": "2024-01-15T12:00:00+00:00", "equity": "1050", "open_positions": 0},
        {"time": "2024-02-15T12:00:00+00:00", "equity": "970", "open_positions": 0},
    ]
    result = evaluate_regime_quality(
        regime_labels=labels,
        trades=trades,
        equity=equity,
        run_id="run_x",
        experiment_id="exp_x",
    )
    assert result.artifact["worst_regime"]["trend"] == "BEAR"
    assert result.artifact["strongest_regime"]["trend"] == "BULL"
    assert Decimal(result.artifact["symbols"]["BTC"]) == Decimal("-30")


def test_missing_benchmark_is_not_available() -> None:
    slice_raw = compute_slice_metrics(
        cell_id="BULL|NORMAL_VOL",
        trades=[
            {
                "symbol": "ETH",
                "net_pnl": "10",
                "fees": "0",
                "slippage_cost": "0",
                "funding": "0",
            }
        ],
        equity=[],
    )
    assert slice_raw.to_dict()["benchmark_delta"] == NOT_AVAILABLE
    assert slice_raw.to_dict()["max_drawdown"] == NOT_AVAILABLE


def test_idempotent_quality_id() -> None:
    labels = _labels_two_regimes()
    a = evaluate_regime_quality(
        regime_labels=labels,
        trades=[],
        equity=[],
        run_id="run_1",
        experiment_id="exp_1",
    )
    b = evaluate_regime_quality(
        regime_labels=labels,
        trades=[],
        equity=[],
        run_id="run_1",
        experiment_id="exp_1",
    )
    assert a.quality_id == b.quality_id
    assert a.artifact == b.artifact


def test_seal_roundtrip(tmp_path: Path) -> None:
    labels = _labels_two_regimes()
    result = evaluate_regime_quality(
        regime_labels=labels,
        trades=[],
        equity=[],
        run_id="run_seal",
        experiment_id="exp_seal",
    )
    write_regime_metrics_artifact(tmp_path, result.artifact)
    assert len(verify_regime_metrics_seal(tmp_path)) == 64


def test_score_policy_hash_stable() -> None:
    from research.regime_quality.scoring import compute_score_policy_content_hash

    p = get_score_policy("1.0")
    assert compute_score_policy_content_hash(p) == compute_score_policy_content_hash(p)
