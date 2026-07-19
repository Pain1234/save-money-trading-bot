"""P4.9 scorecard reproducibility + anti-overfit acceptance (#293).

Explicit matrix (Issue #293) — composition over sealed layers, not UI (#292):

1. Valid synthetic run → scorecard with layer pins + no auto-promotion
2. Same inputs → identical ``scorecard_id`` (idempotent)
3. Evidence tamper (JSONL profile) → fail-closed on verify
4. Run artifact byte-tamper without registry update → evaluate fails
5. Missing confidence → derived-at-scorecard (limitation), still no promotion
6. Critical gate FAIL bound into scorecard → overall_status stays fail
7. Invalidation → no silent reactivation
8. Unknown policy version → fail-closed
9. Silent policy content edit under same version string → hash mismatch
10. Parameter-area isolated peak vs broad plateau (unit composition)
11. Behaviour: Sideways zero-trades defensive; Bull whipsaw weakness
12. No automatic promotion flags on any successful evaluate

Non-scope: dashboard UI (#292), private Strategy V1 metrics, paper/live side effects.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from research.artifacts import load_checksums
from research.gate_evaluator import GateEvaluator
from research.parameter_area import NeighborObservation, evaluate_parameter_area
from research.regime_behaviour import derive_regime_labels, get_behaviour_policy
from research.registry import ExperimentRegistry
from research.scorecard_evaluator import (
    ScorecardEvaluationError,
    ScorecardEvaluator,
    ScorecardResultStore,
    scorecard_evidence_content_hash,
    verify_scorecard_record_artifact_checksums,
)
from research.scorecard_policy import (
    SCORECARD_POLICY_1_0_CONTENT_HASH,
    ScorecardPolicy,
    compute_scorecard_policy_content_hash,
    get_scorecard_policy,
    verify_scorecard_policy_content_hash,
)

from tests.research import test_gate_evaluator as te


@pytest.fixture(autouse=True)
def _pin_evaluation_git_sha(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RESEARCH_EVALUATION_GIT_SHA", "a" * 40)
    monkeypatch.delenv("RAILWAY_GIT_COMMIT_SHA", raising=False)


def _evaluator(root: Path) -> ScorecardEvaluator:
    return ScorecardEvaluator(root, repo_root=te._evaluation_image_root(root))


def test_matrix_valid_run_idempotent_same_scorecard_id(tmp_path: Path) -> None:
    root, _experiment_id, run_id = te._completed_run(tmp_path)
    evaluator = _evaluator(root)
    first = evaluator.evaluate(run_id=run_id, policy_version="1.0")
    second = evaluator.evaluate(run_id=run_id, policy_version="1.0")
    assert first.scorecard_id == second.scorecard_id
    assert first.scorecard_id.startswith("sc_")
    assert first.evidence_content_hash == scorecard_evidence_content_hash(first)
    assert first.auto_promotion is False
    assert first.decision_binding is False
    assert first.promotion_action == "none"
    assert first.layer_refs.get("classification_id")
    assert first.layer_refs.get("quality_id")
    assert first.layer_refs.get("behaviour_id")
    assert first.global_profile["auto_promotion"] is False
    assert first.global_profile["decision_binding"] is False
    lines = evaluator.store.path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1


def test_matrix_tampered_scorecard_record_fail_closed(tmp_path: Path) -> None:
    root, _experiment_id, run_id = te._completed_run(tmp_path)
    evaluator = _evaluator(root)
    record = evaluator.evaluate(run_id=run_id, policy_version="1.0")
    lines = evaluator.store.path.read_text(encoding="utf-8").strip().splitlines()
    payload = json.loads(lines[0])
    payload["global_profile"] = {**payload["global_profile"], "tampered": True}
    evaluator.store.path.write_text(
        json.dumps(payload, sort_keys=True) + "\n", encoding="utf-8"
    )
    tampered = ScorecardResultStore(root).get(record.scorecard_id)
    assert tampered is not None
    with pytest.raises(ScorecardEvaluationError, match="evidence_content_hash"):
        verify_scorecard_record_artifact_checksums(root, tampered)


def test_matrix_run_artifact_tamper_blocks_evaluate(tmp_path: Path) -> None:
    root, _experiment_id, run_id = te._completed_run(tmp_path)
    entry = ExperimentRegistry(root).show(run_id, verify=True)
    metrics_path = Path(entry.artifact_path) / "regime_metrics.json"
    raw = metrics_path.read_bytes()
    metrics_path.write_bytes(raw + b"\n")
    # Registry trust anchor still has the old digest — evaluate must fail closed.
    evaluator = _evaluator(root)
    with pytest.raises(ScorecardEvaluationError):
        evaluator.evaluate(run_id=run_id, policy_version="1.0")
    # Confirm registry verify itself fails.
    with pytest.raises((ValueError, FileNotFoundError)):
        ExperimentRegistry(root).show(run_id, verify=True)


def test_matrix_missing_confidence_derived_no_promotion(tmp_path: Path) -> None:
    root, _experiment_id, run_id = te._completed_run(tmp_path)
    entry = ExperimentRegistry(root).show(run_id, verify=True)
    run_dir = Path(entry.artifact_path)
    conf = run_dir / "confidence_profile.json"
    if conf.is_file():
        conf.unlink()
        # Drop from on-disk checksums file only — registry still seals required layers.
        checksums = load_checksums(run_dir)
        checksums.pop("confidence_profile.json", None)
        (run_dir / "checksums.json").write_text(
            json.dumps(checksums, sort_keys=True, indent=2) + "\n", encoding="utf-8"
        )
    record = _evaluator(root).evaluate(run_id=run_id, policy_version="1.0")
    assert record.global_profile["confidence"]["source"] in (
        "derived_at_scorecard",
        "artifact",
    )
    assert record.auto_promotion is False
    assert record.promotion_action == "none"


def test_matrix_critical_gate_fail_not_healed_by_scorecard(tmp_path: Path) -> None:
    root, experiment_id, run_id = te._completed_run(tmp_path)
    neg_a = te._clone_run_with_net_pnl(
        root, run_id, new_run_id="run_fold_neg_a", net_pnl="-10"
    )
    neg_b = te._clone_run_with_net_pnl(
        root, run_id, new_run_id="run_fold_neg_b", net_pnl="-20"
    )
    robustness_id = te._save_walk_forward_manifest(
        root,
        base_experiment_id=experiment_id,
        base_run_id=run_id,
        fold_run_ids=[neg_a, neg_b, run_id],
    )
    gate = GateEvaluator(root, repo_root=te._evaluation_image_root(root)).evaluate(
        run_id=run_id, policy_version="1.0", robustness_run_ids=[robustness_id]
    )
    assert gate.overall_status == "fail"

    scorecard = _evaluator(root).evaluate(
        run_id=run_id,
        policy_version="1.0",
        gate_run_id=gate.gate_run_id,
        robustness_run_ids=[robustness_id],
    )
    assert scorecard.global_profile["gates"]["overall_status"] == "fail"
    assert scorecard.auto_promotion is False
    assert scorecard.promotion_action == "none"
    # Bull/quality layers may still be present — must not flip promotion.
    assert scorecard.layer_refs.get("quality_id")
    assert scorecard.decision_binding is False


def test_matrix_invalidation_blocks_reactivation(tmp_path: Path) -> None:
    root, _experiment_id, run_id = te._completed_run(tmp_path)
    evaluator = _evaluator(root)
    record = evaluator.evaluate(run_id=run_id, policy_version="1.0")
    ScorecardResultStore(root).invalidate(
        record.scorecard_id, reason="acceptance", actor="test"
    )
    with pytest.raises(ScorecardEvaluationError, match="invalidated"):
        evaluator.evaluate(run_id=run_id, policy_version="1.0")


def test_matrix_unknown_policy_version_fail_closed(tmp_path: Path) -> None:
    root, _experiment_id, run_id = te._completed_run(tmp_path)
    with pytest.raises(ScorecardEvaluationError):
        _evaluator(root).evaluate(run_id=run_id, policy_version="9.9")


def test_matrix_policy_content_mutation_under_same_version_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = get_scorecard_policy("1.0")
    assert (
        compute_scorecard_policy_content_hash(original)
        == SCORECARD_POLICY_1_0_CONTENT_HASH
    )
    mutated = ScorecardPolicy(
        version="1.0",
        description="mutated silently under same version string",
        required_layer_files=original.required_layer_files,
        optional_layer_files=original.optional_layer_files,
    )
    monkeypatch.setitem(
        __import__(
            "research.scorecard_policy", fromlist=["_POLICY_REGISTRY"]
        )._POLICY_REGISTRY,
        "1.0",
        mutated,
    )
    with pytest.raises(Exception, match="content hash|mismatch"):
        verify_scorecard_policy_content_hash("1.0", SCORECARD_POLICY_1_0_CONTENT_HASH)


def test_matrix_parameter_area_isolated_vs_broad() -> None:
    frozen = {"daily_ema_period": 20}
    peak = evaluate_parameter_area(
        robustness_id="rob_peak",
        frozen_parameters=frozen,
        observations=[
            NeighborObservation(
                child_id="frozen",
                label="baseline",
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
                net_pnl="-10",
                total_costs="5",
                gate_pass=True,
            ),
            NeighborObservation(
                child_id="neighbor_02",
                label="daily_ema_period=22",
                parameters={"daily_ema_period": 22},
                status="complete",
                net_pnl="-20",
                total_costs="5",
                gate_pass=True,
            ),
        ],
    )
    assert peak.classification == "ISOLATED_PEAK"
    assert peak.artifact["auto_parameter_selection"] is False

    broad = evaluate_parameter_area(
        robustness_id="rob_broad",
        frozen_parameters=frozen,
        observations=[
            NeighborObservation(
                child_id="frozen",
                label="baseline",
                parameters=frozen,
                status="complete",
                net_pnl="50",
                total_costs="5",
                gate_pass=True,
            ),
            NeighborObservation(
                child_id="neighbor_01",
                label="daily_ema_period=18",
                parameters={"daily_ema_period": 18},
                status="complete",
                net_pnl="40",
                total_costs="4",
                gate_pass=True,
            ),
            NeighborObservation(
                child_id="neighbor_02",
                label="daily_ema_period=22",
                parameters={"daily_ema_period": 22},
                status="complete",
                net_pnl="45",
                total_costs="4",
                gate_pass=True,
            ),
            NeighborObservation(
                child_id="neighbor_03",
                label="daily_ema_period=16",
                parameters={"daily_ema_period": 16},
                status="complete",
                net_pnl="30",
                total_costs="3",
                gate_pass=True,
            ),
            NeighborObservation(
                child_id="neighbor_04",
                label="daily_ema_period=24",
                parameters={"daily_ema_period": 24},
                status="complete",
                net_pnl="35",
                total_costs="3",
                gate_pass=True,
            ),
        ],
    )
    assert broad.classification == "BROAD_STABLE_PLATEAU"


def test_matrix_behaviour_sideways_defensive_and_bull_whipsaw() -> None:
    policy = get_behaviour_policy("1.0")
    sideways = derive_regime_labels(
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
        policy,
    )
    assert sideways == ("DEFENSIVE_INACTIVE",)

    bull = derive_regime_labels(
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
        policy,
    )
    assert "WHIPSAW_PRONE" in bull
