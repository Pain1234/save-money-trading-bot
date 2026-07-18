"""Unit/integration tests for the gate evaluator + persistence (Issue #248 / P4.7c).

Mirrors ``tests/research/test_runner_registry.py`` (#143/#145) for the base
completed-run fixture and ``tests/research/test_robustness_builders.py``
(#247) for synthetic robustness manifest fixtures. Public/synthetic BTC
fixture data only — no private Strategy V1 numbers.
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest
from research import gate_policy as gp
from research.artifacts import load_checksums
from research.gate_evaluator import (
    GateEvaluationError,
    GateEvaluator,
    GateResultStore,
    GateRunRecord,
    compute_gate_run_id,
)
from research.registry import ExperimentRegistry
from research.robustness import (
    ROBUSTNESS_MANIFEST_SCHEMA_VERSION,
    RobustnessChildResult,
    RobustnessManifest,
    save_robustness_manifest,
)
from research.runner import RunRequest, run_experiment

from tests.research.fixtures import REPO_ROOT, align_spec_to_bundle, btc_bundle


def _completed_run(tmp_path: Path) -> tuple[Path, str, str]:
    """Build + register one completed run; return (artifacts_root, experiment_id, run_id)."""
    bundle = btc_bundle()
    spec = align_spec_to_bundle(tmp_path, bundle)
    out_root = tmp_path / "out"
    outcome = run_experiment(
        RunRequest(
            spec=spec,
            bundle=bundle,
            artifacts_root=out_root,
            repo_root=REPO_ROOT,
            allow_dirty_git=True,
        )
    )
    assert outcome.status == "complete", outcome.error
    run_dir = outcome.artifact_path
    assert run_dir is not None

    from research.__main__ import _cost_model_version_from_run

    registry = ExperimentRegistry(out_root)
    registry.register_complete(
        experiment_id=outcome.experiment_id,
        run_id=outcome.run_id,
        attempt_id=outcome.attempt_id,
        strategy_version=spec.strategy_version,
        dataset_version=spec.dataset_manifest_ref.dataset_id,
        cost_model_version=_cost_model_version_from_run(run_dir),
        benchmark_ref=spec.benchmark,
        artifact_path=run_dir,
        checksums=load_checksums(run_dir),
    )
    return out_root, outcome.experiment_id, outcome.run_id


def _save_walk_forward_manifest(
    root: Path, *, base_experiment_id: str, base_run_id: str, fold_net_pnls: list[str]
) -> str:
    robustness_id = "rob_test_walk_forward"
    children = tuple(
        RobustnessChildResult(
            child_id=f"fold_{i:02d}",
            label=f"fold_{i:02d}",
            experiment_id=base_experiment_id,
            run_id=base_run_id,
            status="complete",
            net_pnl=pnl,
        )
        for i, pnl in enumerate(fold_net_pnls, start=1)
    )
    manifest = RobustnessManifest(
        schema_version=ROBUSTNESS_MANIFEST_SCHEMA_VERSION,
        robustness_id=robustness_id,
        test_type="walk_forward",
        base_experiment_id=base_experiment_id,
        base_run_id=base_run_id,
        dataset_catalog_id=None,
        config={},
        created_at="2024-01-01T00:00:00.000000Z",
        children=children,
        bootstrap_result=None,
        summary={"n_children": len(children), "n_complete": len(children), "n_failed": 0},
    )
    save_robustness_manifest(root, manifest)
    return robustness_id


def test_evaluate_binds_required_evidence_fields(tmp_path: Path) -> None:
    root, experiment_id, run_id = _completed_run(tmp_path)
    evaluator = GateEvaluator(root, repo_root=REPO_ROOT)

    record = evaluator.evaluate(run_id=run_id, policy_version="1.0")

    assert record.gate_run_id.startswith("gate_")
    assert record.experiment_id == experiment_id
    assert record.run_id == run_id
    assert record.policy_version == "1.0"
    assert len(record.policy_content_hash) == 64
    assert record.run_code_commit
    assert record.evaluation_code_commit
    assert record.dataset_id
    assert len(record.dataset_content_hash) == 64
    assert record.artifact_checksums, "must bind checksums of evaluated evidence"
    assert record.promotion_action == "none"
    assert record.overall_status in {"pass", "fail"}
    assert record.status == "active"
    assert len(record.gates) == len(gp.get_policy("1.0").gates)


def test_evaluate_records_measurements_for_audit(tmp_path: Path) -> None:
    root, _experiment_id, run_id = _completed_run(tmp_path)
    evaluator = GateEvaluator(root, repo_root=REPO_ROOT)
    record = evaluator.evaluate(run_id=run_id, policy_version="1.0")

    assert "closed_trades" in record.measurements
    assert "net_pnl" in record.measurements
    for gate in record.gates:
        if gate.measured_value is not None:
            Decimal(gate.measured_value)  # must be a canonical Decimal string


def test_evaluate_gate_pass_fail_matches_comparator(tmp_path: Path) -> None:
    root, _experiment_id, run_id = _completed_run(tmp_path)
    evaluator = GateEvaluator(root, repo_root=REPO_ROOT)
    record = evaluator.evaluate(run_id=run_id, policy_version="1.0")

    policy = gp.get_policy("1.0")
    by_name = {g.name: g for g in policy.gates}
    for result in record.gates:
        gate_def = by_name[result.name]
        if result.measured_value is None:
            assert result.passed is False
            continue
        expected = gp.evaluate_comparator(
            gate_def.comparator, Decimal(result.measured_value), Decimal(gate_def.threshold)
        )
        assert result.passed == expected
        if not result.passed:
            assert result.reason != "pass"


def test_evaluate_is_idempotent_append_only(tmp_path: Path) -> None:
    root, _experiment_id, run_id = _completed_run(tmp_path)
    evaluator = GateEvaluator(root, repo_root=REPO_ROOT)

    first = evaluator.evaluate(run_id=run_id, policy_version="1.0")
    second = evaluator.evaluate(run_id=run_id, policy_version="1.0")

    assert first.gate_run_id == second.gate_run_id
    store = GateResultStore(root)
    matching = [e for e in store.list_entries() if e.gate_run_id == first.gate_run_id]
    assert len(matching) == 1, "idempotent evaluate must not append a duplicate record"


def test_evaluate_unknown_run_id_raises(tmp_path: Path) -> None:
    evaluator = GateEvaluator(tmp_path, repo_root=REPO_ROOT)
    with pytest.raises(GateEvaluationError):
        evaluator.evaluate(run_id="run_does_not_exist", policy_version="1.0")


def test_evaluate_unknown_policy_version_raises(tmp_path: Path) -> None:
    root, _experiment_id, run_id = _completed_run(tmp_path)
    evaluator = GateEvaluator(root, repo_root=REPO_ROOT)
    with pytest.raises(GateEvaluationError):
        evaluator.evaluate(run_id=run_id, policy_version="999.0")


def test_evaluate_rejects_tampered_run_artifacts(tmp_path: Path) -> None:
    root, _experiment_id, run_id = _completed_run(tmp_path)
    registry = ExperimentRegistry(root)
    entry = registry.show(run_id, verify=False)
    metrics_path = Path(entry.artifact_path) / "metrics.json"
    original = metrics_path.read_bytes()
    metrics_path.write_bytes(original.replace(b"complete", b"complete "))

    evaluator = GateEvaluator(root, repo_root=REPO_ROOT)
    with pytest.raises(Exception):  # noqa: B017 — fail-closed via registry checksum verify
        evaluator.evaluate(run_id=run_id, policy_version="1.0")


def test_walk_forward_manifest_binds_robustness_evidence(tmp_path: Path) -> None:
    root, experiment_id, run_id = _completed_run(tmp_path)
    robustness_id = _save_walk_forward_manifest(
        root,
        base_experiment_id=experiment_id,
        base_run_id=run_id,
        fold_net_pnls=["10", "20", "-5"],
    )

    evaluator = GateEvaluator(root, repo_root=REPO_ROOT)
    record = evaluator.evaluate(
        run_id=run_id, policy_version="1.0", robustness_run_ids=[robustness_id]
    )

    assert record.robustness_run_ids == (robustness_id,)
    assert f"robustness/{robustness_id}/manifest.json" in record.artifact_checksums
    assert record.measurements["walk_forward_fold_pass_ratio"] == "0.6666666666666666666666666667"
    wf_gate = next(g for g in record.gates if g.name == "walk_forward_fold_pass_ratio")
    assert wf_gate.passed is True


def test_walk_forward_manifest_failing_ratio_fails_gate(tmp_path: Path) -> None:
    root, experiment_id, run_id = _completed_run(tmp_path)
    robustness_id = _save_walk_forward_manifest(
        root,
        base_experiment_id=experiment_id,
        base_run_id=run_id,
        fold_net_pnls=["-10", "-20", "5"],
    )

    evaluator = GateEvaluator(root, repo_root=REPO_ROOT)
    record = evaluator.evaluate(
        run_id=run_id, policy_version="1.0", robustness_run_ids=[robustness_id]
    )
    wf_gate = next(g for g in record.gates if g.name == "walk_forward_fold_pass_ratio")
    assert wf_gate.passed is False
    assert record.overall_status == "fail"


def test_evaluate_missing_robustness_manifest_raises(tmp_path: Path) -> None:
    root, _experiment_id, run_id = _completed_run(tmp_path)
    evaluator = GateEvaluator(root, repo_root=REPO_ROOT)
    with pytest.raises(GateEvaluationError):
        evaluator.evaluate(
            run_id=run_id, policy_version="1.0", robustness_run_ids=["rob_missing"]
        )


def test_store_append_rejects_duplicate_active_gate_run_id(tmp_path: Path) -> None:
    store = GateResultStore(tmp_path)
    record = GateRunRecord(
        schema_version="1.0",
        gate_run_id="gate_dup",
        policy_version="1.0",
        policy_content_hash="a" * 64,
        evaluated_at="2024-01-01T00:00:00.000000Z",
        run_code_commit="0" * 40,
        evaluation_code_commit="0" * 40,
        experiment_id="exp_x",
        run_id="run_x",
        robustness_run_ids=(),
        dataset_id="ds_x",
        dataset_content_hash="b" * 64,
        artifact_checksums={"metrics.json": "c" * 64},
        measurements={"net_pnl": "1"},
        gates=(),
        overall_status="pass",
    )
    store.append(record)
    with pytest.raises(ValueError):
        store.append(record)


def test_invalidate_appends_sidecar_without_mutating_original(tmp_path: Path) -> None:
    root, _experiment_id, run_id = _completed_run(tmp_path)
    evaluator = GateEvaluator(root, repo_root=REPO_ROOT)
    record = evaluator.evaluate(run_id=run_id, policy_version="1.0")

    store = GateResultStore(root)
    original_line_count = len(store.list_entries())
    sidecar = store.invalidate(record.gate_run_id, reason="fixture correction", actor="test")

    assert sidecar.is_file()
    entries = store.list_entries()
    assert len(entries) == original_line_count + 1, "invalidation must append, not rewrite"
    first_entry = entries[0]
    assert first_entry.status == "active"
    assert first_entry.overall_status == record.overall_status  # original untouched

    latest = store.get(record.gate_run_id)
    assert latest is not None
    assert latest.status == "invalidated"
    assert latest.invalidation_reason == "fixture correction"


def test_double_invalidate_raises(tmp_path: Path) -> None:
    root, _experiment_id, run_id = _completed_run(tmp_path)
    evaluator = GateEvaluator(root, repo_root=REPO_ROOT)
    record = evaluator.evaluate(run_id=run_id, policy_version="1.0")

    store = GateResultStore(root)
    store.invalidate(record.gate_run_id, reason="first", actor="test")
    with pytest.raises(ValueError):
        store.invalidate(record.gate_run_id, reason="second", actor="test")


def test_invalidate_unknown_gate_run_id_raises(tmp_path: Path) -> None:
    store = GateResultStore(tmp_path)
    with pytest.raises(KeyError):
        store.invalidate("gate_missing", reason="x", actor="test")


def test_gate_run_id_is_deterministic_and_policy_bound() -> None:
    a = compute_gate_run_id(
        run_id="run_x", policy_version="1.0", policy_content_hash="h1"
    )
    b = compute_gate_run_id(
        run_id="run_x", policy_version="1.0", policy_content_hash="h1"
    )
    c = compute_gate_run_id(
        run_id="run_x", policy_version="1.0", policy_content_hash="h2"
    )
    assert a == b
    assert a != c


def test_persisted_record_detects_policy_content_changed_under_same_version(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Reproduces the mandatory #248 requirement: a persisted GateRunRecord's
    policy_content_hash must reject re-verification once the in-repo policy
    for that SAME version string has been silently edited."""
    root, _experiment_id, run_id = _completed_run(tmp_path)
    evaluator = GateEvaluator(root, repo_root=REPO_ROOT)
    record = evaluator.evaluate(run_id=run_id, policy_version="1.0")

    # Sanity: verification passes against the unmodified in-repo policy.
    gp.verify_policy_content_hash(record.policy_version, record.policy_content_hash)

    edited_policy = gp.GatePolicy(
        version="1.0",
        description=gp.get_policy("1.0").description,
        gates=(
            gp.GateDefinition(
                name="min_closed_trades",
                metric="closed_trades",
                comparator="gte",
                threshold="999999",
            ),
        ),
    )
    monkeypatch.setitem(gp._POLICY_REGISTRY, "1.0", edited_policy)

    with pytest.raises(gp.GatePolicyError, match="content hash mismatch"):
        gp.verify_policy_content_hash(record.policy_version, record.policy_content_hash)
