"""Tests for parameter-area / plateau classification (#290)."""

from __future__ import annotations

import pytest
from research.parameter_area import (
    NeighborObservation,
    ParameterAreaError,
    evaluate_parameter_area,
    evaluate_parameter_area_from_robustness,
    get_parameter_area_policy,
    write_parameter_area_artifact,
)
from research.parameter_area.policy import compute_policy_content_hash


def _policy():
    return get_parameter_area_policy("1.0")


def _obs(
    child_id: str,
    *,
    params: dict,
    net_pnl: str,
    total_costs: str = "1",
    gate_pass: bool | None = True,
    status: str = "complete",
    label: str | None = None,
) -> NeighborObservation:
    return NeighborObservation(
        child_id=child_id,
        label=label or child_id,
        parameters=params,
        status=status,
        net_pnl=net_pnl,
        total_costs=total_costs,
        gate_pass=gate_pass,
    )


def test_isolated_peak_when_only_frozen_stable() -> None:
    frozen = {"daily_ema_period": 20, "atr_period": 14}
    observations = [
        _obs("frozen", params=frozen, net_pnl="100", total_costs="5"),
        _obs(
            "neighbor_01",
            params={"daily_ema_period": 18, "atr_period": 14},
            net_pnl="-10",
            total_costs="5",
            label="daily_ema_period=18",
        ),
        _obs(
            "neighbor_02",
            params={"daily_ema_period": 22, "atr_period": 14},
            net_pnl="-20",
            total_costs="5",
            label="daily_ema_period=22",
        ),
        _obs(
            "neighbor_03",
            params={"daily_ema_period": 20, "atr_period": 12},
            net_pnl="-5",
            total_costs="5",
            label="atr_period=12",
        ),
        _obs(
            "neighbor_04",
            params={"daily_ema_period": 20, "atr_period": 16},
            net_pnl="-8",
            total_costs="5",
            label="atr_period=16",
        ),
    ]
    result = evaluate_parameter_area(
        robustness_id="rob_peak",
        frozen_parameters=frozen,
        observations=observations,
    )
    assert result.classification == "ISOLATED_PEAK"
    art = result.artifact
    assert art["frozen_point"]["unchanged"] is True
    assert art["frozen_point"]["auto_selected"] is False
    assert art["auto_parameter_selection"] is False
    assert art["oos_holdout_used"] is False
    assert art["decision_binding"] is False
    assert art["evidence_trusted"] is False
    assert art["plateau"]["isolated_optimum"] is True


def test_broad_stable_plateau_contiguous_axis() -> None:
    frozen = {"daily_ema_period": 20}
    observations = [
        _obs("frozen", params=frozen, net_pnl="50", total_costs="5"),
        _obs(
            "neighbor_01",
            params={"daily_ema_period": 18},
            net_pnl="40",
            total_costs="4",
            label="daily_ema_period=18",
        ),
        _obs(
            "neighbor_02",
            params={"daily_ema_period": 22},
            net_pnl="45",
            total_costs="4",
            label="daily_ema_period=22",
        ),
        _obs(
            "neighbor_03",
            params={"daily_ema_period": 16},
            net_pnl="30",
            total_costs="3",
            label="daily_ema_period=16",
        ),
        _obs(
            "neighbor_04",
            params={"daily_ema_period": 24},
            net_pnl="35",
            total_costs="3",
            label="daily_ema_period=24",
        ),
    ]
    result = evaluate_parameter_area(
        robustness_id="rob_broad",
        frozen_parameters=frozen,
        observations=observations,
    )
    assert result.classification == "BROAD_STABLE_PLATEAU"
    art = result.artifact
    assert art["plateau"]["size"] >= 3
    assert art["plateau"]["includes_frozen"] is True
    assert art["stats"]["gates_available"] is True
    assert float(art["stats"]["share_stable"]) >= 0.6


def test_frozen_unstable_cannot_be_broad_plateau() -> None:
    """Stable neighbors without a stable frozen point must not yield BROAD."""
    frozen = {"daily_ema_period": 20}
    observations = [
        _obs("frozen", params=frozen, net_pnl="-50", total_costs="5"),
        _obs(
            "neighbor_01",
            params={"daily_ema_period": 18},
            net_pnl="40",
            total_costs="4",
        ),
        _obs(
            "neighbor_02",
            params={"daily_ema_period": 22},
            net_pnl="45",
            total_costs="4",
        ),
        _obs(
            "neighbor_03",
            params={"daily_ema_period": 16},
            net_pnl="30",
            total_costs="3",
        ),
    ]
    result = evaluate_parameter_area(
        robustness_id="rob_unfrozen",
        frozen_parameters=frozen,
        observations=observations,
    )
    assert result.classification == "UNSTABLE"
    assert result.artifact["plateau"]["includes_frozen"] is False
    assert result.classification != "BROAD_STABLE_PLATEAU"


def test_frozen_parameter_mismatch_rejected() -> None:
    frozen = {"daily_ema_period": 20}
    observations = [
        _obs("frozen", params={"daily_ema_period": 999}, net_pnl="100", total_costs="1"),
        _obs(
            "neighbor_01",
            params={"daily_ema_period": 18},
            net_pnl="40",
            total_costs="1",
        ),
        _obs(
            "neighbor_02",
            params={"daily_ema_period": 22},
            net_pnl="45",
            total_costs="1",
        ),
    ]
    with pytest.raises(ParameterAreaError, match="frozen observation parameters"):
        evaluate_parameter_area(
            robustness_id="rob_mismatch",
            frozen_parameters=frozen,
            observations=observations,
        )


def test_direct_api_cannot_mark_evidence_trusted() -> None:
    """Public evaluate_parameter_area must not accept a trust bypass."""
    frozen = {"daily_ema_period": 20, "strategy_id": "trend_v1"}
    observations = [
        _obs("frozen", params=frozen, net_pnl="50", total_costs="5"),
        _obs(
            "neighbor_01",
            params={"daily_ema_period": 18, "strategy_id": "trend_v1"},
            net_pnl="40",
            total_costs="4",
        ),
        _obs(
            "neighbor_02",
            params={"daily_ema_period": 22, "strategy_id": "trend_v1"},
            net_pnl="45",
            total_costs="4",
        ),
    ]
    result = evaluate_parameter_area(
        robustness_id="rob_untrusted",
        frozen_parameters=frozen,
        observations=observations,
    )
    assert result.artifact["evidence_trusted"] is False
    assert result.artifact["trusted_manifest_hash"] is None
    # Keyword trust flags must not be accepted on the public API.
    with pytest.raises(TypeError):
        evaluate_parameter_area(  # type: ignore[call-arg]
            robustness_id="rob_bypass",
            frozen_parameters=frozen,
            observations=observations,
            evidence_trusted=True,
            trusted_manifest_hash="deadbeef",
        )


def test_frozen_strategy_id_mismatch_rejected() -> None:
    frozen = {"daily_ema_period": 20, "strategy_id": "trend_v1"}
    observations = [
        _obs(
            "frozen",
            params={"daily_ema_period": 20, "strategy_id": "other_strategy"},
            net_pnl="100",
            total_costs="1",
        ),
        _obs(
            "neighbor_01",
            params={"daily_ema_period": 18, "strategy_id": "other_strategy"},
            net_pnl="40",
            total_costs="1",
        ),
        _obs(
            "neighbor_02",
            params={"daily_ema_period": 22, "strategy_id": "other_strategy"},
            net_pnl="45",
            total_costs="1",
        ),
    ]
    with pytest.raises(ParameterAreaError, match="frozen observation parameters"):
        evaluate_parameter_area(
            robustness_id="rob_strategy",
            frozen_parameters=frozen,
            observations=observations,
        )


def test_from_robustness_requires_trusted_manifest_hash(tmp_path) -> None:
    with pytest.raises(ParameterAreaError, match="trusted_manifest_hash"):
        evaluate_parameter_area_from_robustness(
            tmp_path,
            "rob_missing",
            trusted_manifest_hash="",
            registry=None,  # type: ignore[arg-type]
        )


def test_break_even_not_counted_as_positive() -> None:
    frozen = {"daily_ema_period": 20}
    observations = [
        _obs("frozen", params=frozen, net_pnl="10", total_costs="1"),
        _obs(
            "neighbor_01",
            params={"daily_ema_period": 18},
            net_pnl="0",
            total_costs="1",
        ),
        _obs(
            "neighbor_02",
            params={"daily_ema_period": 22},
            net_pnl="0",
            total_costs="1",
        ),
    ]
    result = evaluate_parameter_area(
        robustness_id="rob_be",
        frozen_parameters=frozen,
        observations=observations,
    )
    assert result.artifact["stats"]["share_positive"] == "0"
    assert all(n["positive"] is False for n in result.artifact["neighbors"])


def test_profit_alone_insufficient_without_costs() -> None:
    frozen = {"daily_ema_period": 20}
    observations = [
        NeighborObservation(
            child_id="frozen",
            label="frozen",
            parameters=frozen,
            status="complete",
            net_pnl="100",
            total_costs="5",
            gate_pass=True,
        ),
        NeighborObservation(
            child_id="neighbor_01",
            label="daily_ema_period=18",
            parameters={"daily_ema_period": 18},
            status="complete",
            net_pnl="80",
            total_costs=None,
            gate_pass=True,
        ),
        NeighborObservation(
            child_id="neighbor_02",
            label="daily_ema_period=22",
            parameters={"daily_ema_period": 22},
            status="complete",
            net_pnl="90",
            total_costs=None,
            gate_pass=True,
        ),
    ]
    result = evaluate_parameter_area(
        robustness_id="rob_cost",
        frozen_parameters=frozen,
        observations=observations,
    )
    assert result.classification in ("ISOLATED_PEAK", "UNSTABLE", "INSUFFICIENT_EVIDENCE")
    assert all(
        (n["stable"] is False) or n["child_id"] == "frozen"
        for n in result.artifact["neighbors"]
    )


def test_insufficient_evidence_too_few_neighbors() -> None:
    frozen = {"daily_ema_period": 20}
    observations = [
        _obs("frozen", params=frozen, net_pnl="10", total_costs="1"),
        _obs(
            "neighbor_01",
            params={"daily_ema_period": 18},
            net_pnl="8",
            total_costs="1",
        ),
    ]
    result = evaluate_parameter_area(
        robustness_id="rob_few",
        frozen_parameters=frozen,
        observations=observations,
    )
    assert result.classification == "INSUFFICIENT_EVIDENCE"


def test_narrow_when_gates_missing_blocks_broad() -> None:
    frozen = {"daily_ema_period": 20}
    observations = [
        NeighborObservation(
            child_id="frozen",
            label="baseline",
            parameters=frozen,
            status="complete",
            net_pnl="50",
            total_costs="5",
            gate_pass=None,
        ),
        NeighborObservation(
            child_id="neighbor_01",
            label="daily_ema_period=18",
            parameters={"daily_ema_period": 18},
            status="complete",
            net_pnl="40",
            total_costs="4",
            gate_pass=None,
        ),
        NeighborObservation(
            child_id="neighbor_02",
            label="daily_ema_period=22",
            parameters={"daily_ema_period": 22},
            status="complete",
            net_pnl="45",
            total_costs="4",
            gate_pass=None,
        ),
        NeighborObservation(
            child_id="neighbor_03",
            label="daily_ema_period=16",
            parameters={"daily_ema_period": 16},
            status="complete",
            net_pnl="30",
            total_costs="3",
            gate_pass=None,
        ),
    ]
    result = evaluate_parameter_area(
        robustness_id="rob_narrow",
        frozen_parameters=frozen,
        observations=observations,
    )
    assert result.classification == "NARROW_STABLE_AREA"
    assert result.artifact["stats"]["share_gate_pass"] == "NOT_AVAILABLE"


def test_policy_hash_stable_and_seal(tmp_path) -> None:
    p = _policy()
    assert compute_policy_content_hash(p) == compute_policy_content_hash(p)
    frozen = {"daily_ema_period": 20}
    result = evaluate_parameter_area(
        robustness_id="rob_seal",
        frozen_parameters=frozen,
        observations=[
            _obs("frozen", params=frozen, net_pnl="1", total_costs="0"),
            _obs(
                "neighbor_01",
                params={"daily_ema_period": 18},
                net_pnl="1",
                total_costs="0",
            ),
            _obs(
                "neighbor_02",
                params={"daily_ema_period": 22},
                net_pnl="1",
                total_costs="0",
            ),
        ],
    )
    path = write_parameter_area_artifact(tmp_path, result.artifact)
    assert path.name == "parameter_area.json"
    assert (tmp_path / "parameter_area.json.sha256").is_file()


def test_evidence_hash_binds_neighbor_results() -> None:
    frozen = {"daily_ema_period": 20}
    base_obs = [
        _obs("frozen", params=frozen, net_pnl="50", total_costs="5"),
        _obs(
            "neighbor_01",
            params={"daily_ema_period": 18},
            net_pnl="40",
            total_costs="4",
        ),
        _obs(
            "neighbor_02",
            params={"daily_ema_period": 22},
            net_pnl="45",
            total_costs="4",
        ),
    ]
    a = evaluate_parameter_area(
        robustness_id="rob_id",
        frozen_parameters=frozen,
        observations=base_obs,
    )
    alt = [
        _obs("frozen", params=frozen, net_pnl="50", total_costs="5"),
        _obs(
            "neighbor_01",
            params={"daily_ema_period": 18},
            net_pnl="-100",
            total_costs="4",
        ),
        _obs(
            "neighbor_02",
            params={"daily_ema_period": 22},
            net_pnl="45",
            total_costs="4",
        ),
    ]
    b = evaluate_parameter_area(
        robustness_id="rob_id",
        frozen_parameters=frozen,
        observations=alt,
    )
    assert a.parameter_area_id != b.parameter_area_id
