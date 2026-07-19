"""P4.9 scorecard reproducibility + anti-overfit acceptance (#293).

Explicit matrix (Issue #293) — Research API / evaluator composition over sealed
layers. Dashboard UI E2E remains out of scope here and is tracked on
[#292](https://github.com/Pain1234/save-money-trading-bot/issues/292) /
[#250](https://github.com/Pain1234/save-money-trading-bot/issues/250); this
issue's "UI E2E" AC is deferred until those land.

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
11. Untrusted parameter_area.json → scorecard evaluate fail-closed
12. Trusted parameter_area (sealed manifest pin) → pins into scorecard
13. integrity_status=INVALID → quality_scores_permitted False
14. Behaviour: Sideways zero-trades defensive; Bull whipsaw weakness
15. API smoke without RESEARCH_ALLOW_DIRTY_GIT (clean temp git tree)
16. No automatic promotion flags on any successful evaluate

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


def _reseal_registry_entry(root: Path, run_id: str) -> None:
    """Recompute run-dir checksums and rewrite the latest registry line for ``run_id``."""
    from research.artifacts import compute_artifact_checksums

    registry = ExperimentRegistry(root)
    entry = registry.show(run_id, verify=False)
    run_dir = Path(entry.artifact_path)
    checksums = compute_artifact_checksums(run_dir)
    (run_dir / "checksums.json").write_text(
        json.dumps(checksums, sort_keys=True, indent=2) + "\n", encoding="utf-8"
    )
    path = registry.path
    lines = path.read_text(encoding="utf-8").strip().splitlines()
    rewritten: list[str] = []
    for line in lines:
        payload = json.loads(line)
        if payload.get("run_id") == run_id:
            payload["checksums"] = checksums
        rewritten.append(json.dumps(payload, sort_keys=True))
    path.write_text("\n".join(rewritten) + "\n", encoding="utf-8")


def test_matrix_insufficient_sample_cannot_yield_high_confidence(tmp_path: Path) -> None:
    """Low closed_trades via derived confidence must not produce HIGH overall."""
    root, _experiment_id, run_id = te._completed_run(tmp_path)
    entry = ExperimentRegistry(root).show(run_id, verify=True)
    run_dir = Path(entry.artifact_path)
    metrics_path = run_dir / "metrics.json"
    metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
    metrics["closed_trades"] = 3
    metrics_path.write_text(
        json.dumps(metrics, sort_keys=True, indent=2) + "\n", encoding="utf-8"
    )
    conf = run_dir / "confidence_profile.json"
    if conf.is_file():
        conf.unlink()
    _reseal_registry_entry(root, run_id)

    record = _evaluator(root).evaluate(run_id=run_id, policy_version="1.0")
    label = record.global_profile["confidence"]["overall_label"]
    assert label in {"INSUFFICIENT", "LOW", "NOT_AVAILABLE", "MEDIUM"}
    assert label != "HIGH"
    assert record.auto_promotion is False


def test_matrix_untrusted_parameter_area_fail_closed(tmp_path: Path) -> None:
    """Public evaluate_parameter_area artifacts must not enter the scorecard."""
    from research.parameter_area import (
        NeighborObservation,
        evaluate_parameter_area,
        write_parameter_area_artifact,
    )

    root, _experiment_id, run_id = te._completed_run(tmp_path)
    entry = ExperimentRegistry(root).show(run_id, verify=True)
    run_dir = Path(entry.artifact_path)
    frozen = {"daily_ema_period": 20}
    result = evaluate_parameter_area(
        robustness_id="rob_peak_sc",
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
    assert result.classification == "ISOLATED_PEAK"
    assert result.artifact.get("evidence_trusted") is False
    write_parameter_area_artifact(run_dir, result.artifact)
    _reseal_registry_entry(root, run_id)

    with pytest.raises(ScorecardEvaluationError) as exc:
        _evaluator(root).evaluate(run_id=run_id, policy_version="1.0")
    assert exc.value.field_errors.get("parameter_area") == "untrusted"


def test_matrix_forged_trusted_parameter_area_fail_closed(tmp_path: Path) -> None:
    """Hand-built evidence_trusted=true without sealed PS recompute must fail."""
    from research.parameter_area import write_parameter_area_artifact

    root, experiment_id, run_id = te._completed_run(tmp_path)
    # Walk-forward seal alone is not enough — recompute requires parameter_stability.
    robustness_id = te._save_walk_forward_manifest(
        root,
        base_experiment_id=experiment_id,
        base_run_id=run_id,
        fold_run_ids=[run_id, run_id, run_id],
        robustness_id="rob_pa_forged",
    )
    job = __import__(
        "research.robustness_jobs", fromlist=["RobustnessJobStore"]
    ).RobustnessJobStore(root).get(robustness_id)
    assert job is not None and job.manifest_content_hash
    entry = ExperimentRegistry(root).show(run_id, verify=True)
    run_dir = Path(entry.artifact_path)
    artifact = {
        "schema_version": "1.0",
        "parameter_area_id": "pa_forged",
        "robustness_id": robustness_id,
        "policy_version": "1.0",
        "policy_content_hash": "c" * 64,
        "evidence_hash": "d" * 64,
        "evidence_trusted": True,
        "trusted_manifest_hash": job.manifest_content_hash,
        "classification": "ISOLATED_PEAK",
        "classification_reason": "forged",
        "auto_parameter_selection": False,
        "decision_binding": False,
        "oos_holdout_used": False,
    }
    write_parameter_area_artifact(run_dir, artifact)
    _reseal_registry_entry(root, run_id)

    with pytest.raises(ScorecardEvaluationError) as exc:
        _evaluator(root).evaluate(run_id=run_id, policy_version="1.0")
    assert exc.value.field_errors.get("parameter_area") in {
        "recompute failed",
        "policy_content_hash mismatch",
        "parameter_area_id mismatch",
    }


def _save_parameter_stability_neighborhood(
    root: Path,
    *,
    experiment_id: str,
    base_run_id: str,
    robustness_id: str = "rob_pa_ps",
) -> str:
    """Seal a minimal parameter_stability neighborhood (frozen + ±1 atr_period)."""
    import shutil

    from research.artifacts import compute_artifact_checksums
    from research.robustness import (
        ROBUSTNESS_MANIFEST_SCHEMA_VERSION,
        RobustnessChildResult,
        RobustnessManifest,
        save_robustness_manifest,
    )
    from research.robustness_jobs import RobustnessJob, RobustnessJobStore

    registry = ExperimentRegistry(root)
    base = registry.show(base_run_id, verify=True)
    base_dir = Path(base.artifact_path)
    experiment = json.loads((base_dir / "experiment.json").read_text(encoding="utf-8"))
    frozen = dict(experiment["parameters"])
    assert "atr_period" in frozen
    atr = int(frozen["atr_period"])
    config = {
        "int_deltas": {"atr_period": [-1, 1]},
        "decimal_relative_steps": {},
    }

    def _clone_neighbor(child_id: str, atr_value: int) -> str:
        new_run_id = f"{base_run_id}_{child_id}"
        dst = base_dir.parent / new_run_id
        shutil.copytree(base_dir, dst)
        exp = json.loads((dst / "experiment.json").read_text(encoding="utf-8"))
        exp["parameters"] = {**frozen, "atr_period": atr_value}
        (dst / "experiment.json").write_text(
            json.dumps(exp, sort_keys=True, indent=2) + "\n", encoding="utf-8"
        )
        checksums = compute_artifact_checksums(dst)
        (dst / "checksums.json").write_text(
            json.dumps(checksums, sort_keys=True, indent=2) + "\n", encoding="utf-8"
        )
        registry.register_complete(
            experiment_id=experiment_id,
            run_id=new_run_id,
            attempt_id=f"{new_run_id}_attempt",
            strategy_version=base.strategy_version,
            dataset_version=base.dataset_version,
            cost_model_version=base.cost_model_version,
            benchmark_ref=base.benchmark_ref,
            artifact_path=dst,
            checksums=checksums,
        )
        return new_run_id

    n1 = _clone_neighbor("neighbor_01", atr - 1)
    n2 = _clone_neighbor("neighbor_02", atr + 1)
    children = (
        RobustnessChildResult(
            child_id="frozen",
            label="baseline",
            experiment_id=experiment_id,
            run_id=base_run_id,
            status="complete",
        ),
        RobustnessChildResult(
            child_id="neighbor_01",
            label=f"atr_period={atr - 1}",
            experiment_id=experiment_id,
            run_id=n1,
            status="complete",
        ),
        RobustnessChildResult(
            child_id="neighbor_02",
            label=f"atr_period={atr + 1}",
            experiment_id=experiment_id,
            run_id=n2,
            status="complete",
        ),
    )
    manifest = RobustnessManifest(
        schema_version=ROBUSTNESS_MANIFEST_SCHEMA_VERSION,
        robustness_id=robustness_id,
        test_type="parameter_stability",
        base_experiment_id=experiment_id,
        base_run_id=base_run_id,
        dataset_catalog_id=None,
        config=config,
        created_at="2024-01-01T00:00:00.000000Z",
        children=children,
        bootstrap_result=None,
        summary={"n_children": 3, "n_complete": 3, "n_failed": 0},
    )
    _path, digest = save_robustness_manifest(root, manifest)
    RobustnessJobStore(root).save(
        RobustnessJob(
            robustness_id=robustness_id,
            base_experiment_id=experiment_id,
            base_run_id=base_run_id,
            test_type="parameter_stability",
            status="completed",
            created_at="2024-01-01T00:00:00.000000Z",
            updated_at="2024-01-01T00:00:00.000000Z",
            finished_at="2024-01-01T00:00:00.000000Z",
            config=config,
            manifest_content_hash=digest,
        )
    )
    return robustness_id


def test_matrix_trusted_parameter_area_pins_into_scorecard(tmp_path: Path) -> None:
    """Real from_robustness artifact + permanent seal on the scorecard record."""
    from research.parameter_area import (
        evaluate_parameter_area_from_robustness,
        write_parameter_area_artifact,
    )
    from research.robustness_jobs import RobustnessJobStore
    from research.scorecard_evaluator import verify_scorecard_record_artifact_checksums

    root, experiment_id, run_id = te._completed_run(tmp_path)
    robustness_id = _save_parameter_stability_neighborhood(
        root,
        experiment_id=experiment_id,
        base_run_id=run_id,
        robustness_id="rob_pa_trusted",
    )
    job = RobustnessJobStore(root).get(robustness_id)
    assert job is not None and job.manifest_content_hash
    result = evaluate_parameter_area_from_robustness(
        root,
        robustness_id,
        trusted_manifest_hash=job.manifest_content_hash,
        registry=ExperimentRegistry(root),
    )
    assert result.artifact.get("evidence_trusted") is True

    entry = ExperimentRegistry(root).show(run_id, verify=True)
    run_dir = Path(entry.artifact_path)
    write_parameter_area_artifact(run_dir, result.artifact)
    _reseal_registry_entry(root, run_id)

    scorecard = _evaluator(root).evaluate(run_id=run_id, policy_version="1.0")
    pa = scorecard.global_profile["parameter_area"]
    assert pa.get("evidence_trusted") is True
    assert pa.get("parameter_area_id") == result.parameter_area_id
    assert scorecard.layer_refs.get("parameter_area_id") == result.parameter_area_id
    seal_key = f"robustness/{robustness_id}/manifest.json"
    assert scorecard.artifact_checksums.get(seal_key) == job.manifest_content_hash
    assert scorecard.auto_promotion is False
    # Permanent seal: reverify still ok while manifest exists.
    verify_scorecard_record_artifact_checksums(root, scorecard)


def test_matrix_parameter_area_manifest_missing_breaks_reverify(tmp_path: Path) -> None:
    """Deleting the sealed PA robustness manifest must fail scorecard reverify."""
    import shutil

    from research.parameter_area import (
        evaluate_parameter_area_from_robustness,
        write_parameter_area_artifact,
    )
    from research.robustness import robustness_artifact_dir
    from research.robustness_jobs import RobustnessJobStore
    from research.scorecard_evaluator import verify_scorecard_record_artifact_checksums

    root, experiment_id, run_id = te._completed_run(tmp_path)
    robustness_id = _save_parameter_stability_neighborhood(
        root,
        experiment_id=experiment_id,
        base_run_id=run_id,
        robustness_id="rob_pa_missing",
    )
    job = RobustnessJobStore(root).get(robustness_id)
    assert job is not None and job.manifest_content_hash
    result = evaluate_parameter_area_from_robustness(
        root,
        robustness_id,
        trusted_manifest_hash=job.manifest_content_hash,
        registry=ExperimentRegistry(root),
    )
    entry = ExperimentRegistry(root).show(run_id, verify=True)
    write_parameter_area_artifact(Path(entry.artifact_path), result.artifact)
    _reseal_registry_entry(root, run_id)
    scorecard = _evaluator(root).evaluate(run_id=run_id, policy_version="1.0")

    shutil.rmtree(robustness_artifact_dir(root, robustness_id))
    with pytest.raises(ScorecardEvaluationError) as exc:
        verify_scorecard_record_artifact_checksums(root, scorecard)
    assert "parameter_area" in exc.value.field_errors or "robustness" in str(
        exc.value
    ).lower()


def test_matrix_invalid_integrity_blocks_decision_use_quality(tmp_path: Path) -> None:
    """Real integrity_status=INVALID must block quality_scores_permitted."""
    from research.gate_evaluator import quality_scores_permitted

    root, experiment_id, run_id = te._completed_run(tmp_path)
    entry = ExperimentRegistry(root).show(run_id, verify=True)
    run_dir = Path(entry.artifact_path)
    manifest_path = run_dir / "run_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    # Empty git_commit fails Layer-0 git_commit_binding → integrity INVALID.
    manifest["git_commit"] = ""
    manifest_path.write_text(
        json.dumps(manifest, sort_keys=True, indent=2) + "\n", encoding="utf-8"
    )
    _reseal_registry_entry(root, run_id)

    robustness_id = te._save_bootstrap_manifest(
        root,
        base_experiment_id=experiment_id,
        base_run_id=run_id,
        robustness_id="rob_qi_invalid",
    )
    gate = GateEvaluator(root, repo_root=te._evaluation_image_root(root)).evaluate(
        run_id=run_id, policy_version="1.0", robustness_run_ids=[robustness_id]
    )
    assert gate.integrity_status == "INVALID"
    assert quality_scores_permitted(gate) is False

    scorecard = _evaluator(root).evaluate(
        run_id=run_id,
        policy_version="1.0",
        gate_run_id=gate.gate_run_id,
        robustness_run_ids=[robustness_id],
    )
    assert scorecard.global_profile["gates"]["integrity_status"] == "INVALID"
    assert scorecard.promotion_action == "none"
    assert scorecard.auto_promotion is False


def test_matrix_public_fixtures_have_no_private_edge_markers() -> None:
    """Static guard: acceptance fixtures stay on public synthetic BTC paths."""
    from tests.research.fixtures import btc_bundle

    bundle = btc_bundle()
    dumped = bundle.model_dump_json().lower()
    forbidden = ("private-research", "strategy_v1_private", "holdout_calendar_secret")
    for token in forbidden:
        assert token not in dumped


def _init_clean_git_repo(path: Path) -> str:
    """Create a minimal clean git repo; return HEAD sha (no dirty bypass)."""
    import subprocess

    path.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init"], cwd=path, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "acceptance@example.com"],
        cwd=path,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Acceptance"],
        cwd=path,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "commit", "--allow-empty", "-m", "acceptance-base"],
        cwd=path,
        check=True,
        capture_output=True,
    )
    head = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=path, text=True
    ).strip()
    return head


def test_matrix_api_evaluate_idempotent_without_dirty_git_bypass(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Research API smoke on a clean git tree — no RESEARCH_ALLOW_DIRTY_GIT."""
    import time

    from fastapi.testclient import TestClient
    from paper_trading.readonly_api import app
    from research.api import (
        get_gate_service,
        get_research_service,
        get_research_write_service,
        get_robustness_service,
        get_scorecard_service,
    )
    from research.gate_service import GateService
    from research.robustness_service import RobustnessOrchestrationService
    from research.scorecard_service import ScorecardService
    from research.service import ResearchReadService
    from research.write_service import ResearchWriteService

    from tests.research.fixtures import align_spec_to_bundle, btc_bundle

    clean_repo = tmp_path / "clean_git_repo"
    head = _init_clean_git_repo(clean_repo)

    bundle = btc_bundle()
    spec = align_spec_to_bundle(tmp_path, bundle, symbols=["BTC"])
    bundle_path = tmp_path / "bundle.json"
    bundle_path.write_text(bundle.model_dump_json(), encoding="utf-8")
    ref = spec.dataset_manifest_ref
    catalog = [
        {
            "id": "fixture-btc",
            "label": "BTC fixture",
            "dataset_id": ref.dataset_id,
            "content_hash": ref.content_hash,
            "manifest_path": ref.manifest_path,
            "bundle_path": str(bundle_path),
            "symbols": ["BTC"],
        }
    ]
    catalog_path = tmp_path / "catalog.json"
    catalog_path.write_text(json.dumps(catalog), encoding="utf-8")
    monkeypatch.setenv("RESEARCH_ARTIFACTS_ROOT", str(tmp_path))
    monkeypatch.setenv("RESEARCH_DATASET_CATALOG_PATH", str(catalog_path))
    monkeypatch.setenv("RESEARCH_REPO_ROOT", str(clean_repo))
    monkeypatch.delenv("RESEARCH_ALLOW_DIRTY_GIT", raising=False)
    monkeypatch.setenv("RESEARCH_EVALUATION_GIT_SHA", head)
    eval_root = tmp_path / ".evaluation_image_root"
    eval_root.mkdir()

    app.dependency_overrides[get_research_service] = lambda: ResearchReadService(tmp_path)
    app.dependency_overrides[get_research_write_service] = lambda: ResearchWriteService(
        tmp_path, repo_root=clean_repo, allow_dirty_git=False
    )
    app.dependency_overrides[get_robustness_service] = (
        lambda: RobustnessOrchestrationService(
            tmp_path, repo_root=clean_repo, allow_dirty_git=False
        )
    )
    app.dependency_overrides[get_gate_service] = lambda: GateService(
        tmp_path, repo_root=eval_root
    )
    app.dependency_overrides[get_scorecard_service] = lambda: ScorecardService(
        tmp_path, repo_root=eval_root
    )
    client = TestClient(app)
    try:
        payload = {
            "strategy_id": "trend_v1",
            "strategy_version": spec.strategy_version,
            "name": "scorecard e2e api clean-git",
            "notes": "acceptance without dirty bypass",
            "symbols": ["BTC"],
            "timeframe": "1D",
            "time_range": {
                "start": spec.time_range.start.strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
                "end": spec.time_range.end.strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
            },
            "starting_capital": str(spec.starting_capital),
            "parameters": {k: v for k, v in spec.parameters.items() if k != "strategy_id"},
            "fee_assumption": {
                "entry_fee_rate": str(spec.fee_assumption.entry_fee_rate),
                "exit_fee_rate": str(spec.fee_assumption.exit_fee_rate),
            },
            "slippage_assumption": {
                "slippage_bps": str(spec.slippage_assumption.slippage_bps)
            },
            "random_seed": 7,
            "dataset_catalog_id": "fixture-btc",
            "owner": "test",
        }
        created = client.post("/api/v1/research/experiments", json=payload).json()
        eid = created["experiment_id"]
        assert client.post(f"/api/v1/research/experiments/{eid}/start").status_code == 200
        deadline = time.time() + 60
        status = "queued"
        while time.time() < deadline:
            status = client.get(f"/api/v1/research/experiments/{eid}/status").json()[
                "status"
            ]
            if status in {"completed", "failed"}:
                break
            time.sleep(0.2)
        assert status == "completed", status
        run_id = client.get(f"/api/v1/research/experiments/{eid}").json()["summary"][
            "run_id"
        ]
        first = client.post(
            "/api/v1/research/scorecards/evaluate",
            json={"run_id": run_id, "policy_version": "1.0"},
        )
        assert first.status_code == 200, first.text
        body = first.json()
        assert body["scorecard_id"].startswith("sc_")
        assert body["promotion_action"] == "none"
        assert body["auto_promotion"] is False
        assert body["evidence_integrity"]["ok"] is True
        second = client.post(
            "/api/v1/research/scorecards/evaluate",
            json={"run_id": run_id, "policy_version": "1.0"},
        )
        assert second.status_code == 200
        assert second.json()["scorecard_id"] == body["scorecard_id"]
    finally:
        app.dependency_overrides.pop(get_research_service, None)
        app.dependency_overrides.pop(get_research_write_service, None)
        app.dependency_overrides.pop(get_robustness_service, None)
        app.dependency_overrides.pop(get_gate_service, None)
        app.dependency_overrides.pop(get_scorecard_service, None)
