"""Tests for regime behaviour + transition-risk labels (#289)."""

from __future__ import annotations

from research.regime_behaviour import (
    derive_regime_labels,
    evaluate_behaviour_profile,
    get_behaviour_policy,
    pick_main_weakness,
)
from research.regime_behaviour.policy import compute_policy_content_hash
from research.regime_behaviour.transitions import build_transition_risk_profile


def _policy():
    return get_behaviour_policy("1.0")


def test_sideways_zero_trades_is_defensive_inactive_not_failure() -> None:
    row = {
        "cell_id": "SIDEWAYS|LOW_VOL",
        "trend": "SIDEWAYS",
        "vol": "LOW_VOL",
        "status": "ZERO_ACTIVITY",
        "zero_activity": True,
        "closed_trades": 0,
        "net_pnl": "0",
        "costs": {"fees": "0", "slippage_costs": "0", "funding_costs": "0"},
    }
    labels = derive_regime_labels(row, _policy())
    assert labels == ("DEFENSIVE_INACTIVE",)
    assert "WHIPSAW_PRONE" not in labels


def test_whipsaw_label_from_many_losing_trades() -> None:
    row = {
        "cell_id": "BULL|HIGH_VOL",
        "trend": "BULL",
        "vol": "HIGH_VOL",
        "status": "OK",
        "zero_activity": False,
        "closed_trades": 8,
        "net_pnl": "-40",
        "expectancy": "-5",
        "costs": {"fees": "2", "slippage_costs": "1", "funding_costs": "0"},
        "tail_loss": "NOT_AVAILABLE",
        "pnl_concentration": "NOT_AVAILABLE",
        "time_in_market": "0.4",
    }
    labels = derive_regime_labels(row, _policy())
    assert "WHIPSAW_PRONE" in labels
    assert pick_main_weakness(labels) == "WHIPSAW_PRONE"


def test_profitable_and_cost_intensive() -> None:
    row = {
        "cell_id": "BULL|NORMAL_VOL",
        "trend": "BULL",
        "vol": "NORMAL_VOL",
        "status": "OK",
        "zero_activity": False,
        "closed_trades": 3,
        "net_pnl": "10",
        "expectancy": "3",
        "costs": {"fees": "8", "slippage_costs": "2", "funding_costs": "0"},
        "tail_loss": "0.01",
        "pnl_concentration": "0.2",
        "time_in_market": "0.5",
    }
    labels = derive_regime_labels(row, _policy())
    assert "PROFITABLE" in labels
    assert "COST_INTENSIVE" in labels


def test_transition_risk_profile_counts() -> None:
    profile = build_transition_risk_profile(
        transitions=[
            {"transition_id": "BULL_TO_BEAR"},
            {"transition_id": "BEAR_TO_BULL"},
        ],
        day_events=[
            {"as_of": "2024-01-28", "event": "TRANSITION_OUT"},
            {"as_of": "2024-02-01", "event": "TRANSITION_IN"},
            {"as_of": "2024-02-10", "event": "STABLE_REGIME"},
        ],
        trades=[
            {
                "exit_time": "2024-02-01T12:00:00+00:00",
                "net_pnl": "-30",
                "fees": "1",
                "slippage_cost": "0",
                "funding": "0",
            }
        ],
    )
    assert profile["transition_count"] == 2
    assert profile["risk_label"] == "HIGH_TRANSITION_RISK"
    assert profile["window_closed_trades"] == 1


def test_evaluate_behaviour_profile_artifact() -> None:
    metrics = {
        "quality_id": "rq_abc",
        "run_id": "run_1",
        "experiment_id": "exp_1",
        "dataset_id": "ds",
        "dataset_content_hash": "a" * 64,
        "decision_binding": False,
        "evidence_status": "OK",
        "regimes": [
            {
                "cell_id": "SIDEWAYS|LOW_VOL",
                "trend": "SIDEWAYS",
                "vol": "LOW_VOL",
                "status": "ZERO_ACTIVITY",
                "zero_activity": True,
                "closed_trades": 0,
                "net_pnl": "0",
                "costs": {"fees": "0", "slippage_costs": "0", "funding_costs": "0"},
            },
            {
                "cell_id": "BULL|HIGH_VOL",
                "trend": "BULL",
                "vol": "HIGH_VOL",
                "status": "OK",
                "zero_activity": False,
                "closed_trades": 8,
                "net_pnl": "-40",
                "expectancy": "-5",
                "costs": {"fees": "2", "slippage_costs": "1", "funding_costs": "0"},
                "tail_loss": "NOT_AVAILABLE",
                "pnl_concentration": "NOT_AVAILABLE",
                "time_in_market": "0.4",
            },
        ],
    }
    labels = {
        "dataset_id": "ds",
        "dataset_content_hash": "a" * 64,
        "transitions": [{"transition_id": "BULL_TO_BEAR"}],
        "day_events": [{"as_of": "2024-01-31", "event": "TRANSITION_OUT"}],
    }
    result = evaluate_behaviour_profile(
        regime_metrics=metrics,
        regime_labels=labels,
        trades=[],
    )
    art = result.artifact
    assert art["llm_source"] is False
    assert art["decision_binding"] is False
    assert art["auto_promotion"] is False
    assert art["human_readable_summary"] is None
    sideways = next(r for r in art["regimes"] if r["trend"] == "SIDEWAYS")
    assert sideways["labels"] == ["DEFENSIVE_INACTIVE"]
    bull = next(r for r in art["regimes"] if r["trend"] == "BULL")
    assert "WHIPSAW_PRONE" in bull["labels"]
    assert art["main_weakness"] == "WHIPSAW_PRONE"
    assert art["main_strength"] == "DEFENSIVE_INACTIVE"
    assert art["transition_risk"]["transition_count"] == 1
    assert art["policy_content_hash"] == compute_policy_content_hash(_policy())


def test_policy_hash_stable() -> None:
    p = _policy()
    assert compute_policy_content_hash(p) == compute_policy_content_hash(p)
