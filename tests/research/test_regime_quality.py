"""Tests for regime quality metrics (#287)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

from research.regime import classify_closes, get_classifier
from research.regime_quality import (
    NOT_AVAILABLE,
    evaluate_regime_quality,
    get_score_policy,
    summarize_slice_score,
    verify_regime_metrics_seal,
    write_regime_metrics_artifact,
)
from research.regime_quality.metrics import compute_slice_metrics


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
            "qty": "1",
            "entry_price": "100",
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
    assert Decimal(bull["costs"]["slippage_costs"]) == Decimal("3")
    assert Decimal(bull["costs"]["funding_costs"]) == Decimal("2")
    assert result.artifact["dataset_id"] == "ds"
    assert result.artifact["run_id"] == "run_test"
    assert result.artifact["decision_binding"] is False
    assert result.artifact["auto_promotion"] is False


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
        dataset_id="ds",
        dataset_content_hash="b" * 64,
    )
    b = evaluate_regime_quality(
        regime_labels=labels,
        trades=[],
        equity=[],
        run_id="run_1",
        experiment_id="exp_1",
        dataset_id="ds",
        dataset_content_hash="b" * 64,
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
