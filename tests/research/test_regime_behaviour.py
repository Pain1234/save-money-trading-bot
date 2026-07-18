"""Tests for regime behaviour + transition-risk labels (#289)."""

from __future__ import annotations

import pytest
from research.regime_behaviour import (
    BehaviourProfileError,
    compute_behaviour_id,
    derive_regime_labels,
    evaluate_behaviour_profile,
    get_behaviour_policy,
    pick_main_weakness,
)
from research.regime_behaviour.evaluator import compute_transition_evidence_hash
from research.regime_behaviour.policy import compute_policy_content_hash
from research.regime_behaviour.transitions import build_transition_risk_profile


def _policy():
    return get_behaviour_policy("1.0")


def _base_metrics(**overrides: object) -> dict:
    base: dict = {
        "quality_id": "rq_abc",
        "run_id": "run_1",
        "experiment_id": "exp_1",
        "dataset_id": "ds",
        "dataset_content_hash": "a" * 64,
        "classification_id": "cl_aaa",
        "classifier_content_hash": "b" * 64,
        "decision_binding": False,
        "evidence_status": "OK",
        "regimes": [],
    }
    base.update(overrides)
    return base


def _base_labels(**overrides: object) -> dict:
    base: dict = {
        "dataset_id": "ds",
        "dataset_content_hash": "a" * 64,
        "classification_id": "cl_aaa",
        "classifier_content_hash": "b" * 64,
        "transitions": [],
        "day_events": [],
    }
    base.update(overrides)
    return base


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


def test_bull_zero_trades_is_late_entry_not_defensive_strength() -> None:
    row = {
        "cell_id": "BULL|LOW_VOL",
        "trend": "BULL",
        "vol": "LOW_VOL",
        "status": "ZERO_ACTIVITY",
        "zero_activity": True,
        "closed_trades": 0,
        "net_pnl": "0",
        "costs": {"fees": "0", "slippage_costs": "0", "funding_costs": "0"},
    }
    labels = derive_regime_labels(row, _policy())
    assert labels == ("LATE_ENTRY",)
    assert "DEFENSIVE_INACTIVE" not in labels


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
    assert pick_main_weakness(labels, _policy().weakness_priority) == "WHIPSAW_PRONE"


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


def test_missing_net_pnl_is_insufficient_not_profitable() -> None:
    row = {
        "cell_id": "BULL|NORMAL_VOL",
        "trend": "BULL",
        "vol": "NORMAL_VOL",
        "status": "OK",
        "zero_activity": False,
        "closed_trades": 2,
        "net_pnl": "NOT_AVAILABLE",
        "costs": {"fees": "0", "slippage_costs": "0", "funding_costs": "0"},
    }
    labels = derive_regime_labels(row, _policy())
    assert labels == ("INSUFFICIENT_EVIDENCE",)


def test_break_even_net_pnl_is_not_profitable() -> None:
    row = {
        "cell_id": "BULL|NORMAL_VOL",
        "trend": "BULL",
        "vol": "NORMAL_VOL",
        "status": "OK",
        "zero_activity": False,
        "closed_trades": 2,
        "net_pnl": "0",
        "expectancy": "0",
        "costs": {"fees": "0", "slippage_costs": "0", "funding_costs": "0"},
        "tail_loss": "0.01",
        "pnl_concentration": "0.2",
        "time_in_market": "0.5",
    }
    labels = derive_regime_labels(row, _policy())
    assert "PROFITABLE" not in labels


def test_transition_risk_profile_counts_and_turnover() -> None:
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
                "quantity": "2",
                "entry_fill_price": "100",
            }
        ],
        policy=_policy(),
    )
    assert profile["transition_count"] == 2
    assert profile["risk_label"] == "HIGH_TRANSITION_RISK"
    assert profile["window_closed_trades"] == 1
    assert profile["window_turnover"] == "200"


def test_evaluate_behaviour_profile_artifact() -> None:
    metrics = _base_metrics(
        regimes=[
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
    )
    labels = _base_labels(
        transitions=[{"transition_id": "BULL_TO_BEAR"}],
        day_events=[{"as_of": "2024-01-31", "event": "TRANSITION_OUT"}],
    )
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
    assert art["evidence_trusted"] is True
    sideways = next(r for r in art["regimes"] if r["trend"] == "SIDEWAYS")
    assert sideways["labels"] == ["DEFENSIVE_INACTIVE"]
    bull = next(r for r in art["regimes"] if r["trend"] == "BULL")
    assert "WHIPSAW_PRONE" in bull["labels"]
    assert art["main_weakness"] == "WHIPSAW_PRONE"
    assert art["main_strength"] == "DEFENSIVE_INACTIVE"
    assert art["transition_risk"]["transition_count"] == 1
    assert art["policy_content_hash"] == compute_policy_content_hash(_policy())
    assert art["classification_id"] == "cl_aaa"
    assert "transition_evidence_hash" in art


def test_inconclusive_evidence_suppresses_positive_labels() -> None:
    metrics = _base_metrics(
        evidence_status="INCONCLUSIVE",
        regimes=[
            {
                "cell_id": "BULL|NORMAL_VOL",
                "trend": "BULL",
                "vol": "NORMAL_VOL",
                "status": "OK",
                "zero_activity": False,
                "closed_trades": 3,
                "net_pnl": "100",
                "expectancy": "30",
                "costs": {"fees": "1", "slippage_costs": "0", "funding_costs": "0"},
                "tail_loss": "0.01",
                "pnl_concentration": "0.2",
                "time_in_market": "0.5",
            },
        ],
    )
    result = evaluate_behaviour_profile(
        regime_metrics=metrics,
        regime_labels=_base_labels(),
    )
    art = result.artifact
    assert art["evidence_trusted"] is False
    assert art["main_strength"] is None
    assert art["main_weakness"] == "INSUFFICIENT_EVIDENCE"
    assert art["regimes"][0]["labels"] == ["INSUFFICIENT_EVIDENCE"]
    assert art["transition_risk"]["risk_label"] == "INSUFFICIENT_EVIDENCE"


def test_behaviour_id_binds_transition_evidence() -> None:
    metrics = _base_metrics(regimes=[])
    labels_a = _base_labels(
        transitions=[{"transition_id": "BULL_TO_BEAR"}],
        day_events=[{"as_of": "2024-01-31", "event": "TRANSITION_OUT"}],
    )
    labels_b = _base_labels(
        transitions=[
            {"transition_id": "BULL_TO_BEAR"},
            {"transition_id": "BEAR_TO_SIDEWAYS"},
            {"transition_id": "SIDEWAYS_TO_BULL"},
        ],
        day_events=[
            {"as_of": "2024-01-31", "event": "TRANSITION_OUT"},
            {"as_of": "2024-02-15", "event": "TRANSITION_IN"},
        ],
    )
    a = evaluate_behaviour_profile(regime_metrics=metrics, regime_labels=labels_a)
    b = evaluate_behaviour_profile(regime_metrics=metrics, regime_labels=labels_b)
    assert a.behaviour_id != b.behaviour_id
    assert a.artifact["transition_risk"]["risk_label"] == "MODERATE_TRANSITION_RISK"
    assert b.artifact["transition_risk"]["risk_label"] == "HIGH_TRANSITION_RISK"


def test_classification_pin_mismatch_rejected() -> None:
    metrics = _base_metrics(regimes=[])
    labels = _base_labels(classification_id="cl_other")
    with pytest.raises(BehaviourProfileError, match="classification_id"):
        evaluate_behaviour_profile(regime_metrics=metrics, regime_labels=labels)


def test_policy_hash_includes_late_entry_and_priorities() -> None:
    p = _policy()
    payload = p.to_dict()
    assert "late_entry_time_in_market_max" in payload
    assert "high_transition_count_min" in payload
    assert payload["weakness_priority"][0] == "TAIL_RISK_EXPOSED"
    assert compute_policy_content_hash(p) == compute_policy_content_hash(p)


def test_compute_behaviour_id_stable_for_same_inputs() -> None:
    te = compute_transition_evidence_hash(transitions=[], day_events=[])
    a = compute_behaviour_id(
        run_id="r",
        quality_id="q",
        classification_id="c",
        classifier_content_hash="h",
        transition_evidence_hash=te,
        policy_version="1.0",
        policy_content_hash="p",
    )
    b = compute_behaviour_id(
        run_id="r",
        quality_id="q",
        classification_id="c",
        classifier_content_hash="h",
        transition_evidence_hash=te,
        policy_version="1.0",
        policy_content_hash="p",
    )
    assert a == b
    assert a.startswith("bh_")
