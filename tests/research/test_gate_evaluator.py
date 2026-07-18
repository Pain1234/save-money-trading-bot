"""Unit/integration tests for the gate evaluator + persistence (Issue #248 / P4.7c).

Mirrors ``tests/research/test_runner_registry.py`` (#143/#145) for the base
completed-run fixture and ``tests/research/test_robustness_builders.py``
(#247) for synthetic robustness manifest fixtures. Public/synthetic BTC
fixture data only — no private Strategy V1 numbers.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from decimal import Decimal
from pathlib import Path

import pytest
from research import gate_policy as gp
from research.artifacts import compute_artifact_checksums, load_checksums
from research.gate_evaluator import (
    GateEvaluationError,
    GateEvaluator,
    GateResultStore,
    GateRunRecord,
    compute_gate_run_id,
)
from research.gate_service import GateService
from research.registry import ExperimentRegistry
from research.robustness import (
    ROBUSTNESS_MANIFEST_SCHEMA_VERSION,
    RobustnessChildResult,
    RobustnessManifest,
    compute_bootstrap_from_equity_artifact,
    robustness_manifest_path,
    save_robustness_manifest,
)
from research.runner import RunRequest, run_experiment
from research.write_service import ResearchWriteError

from tests.research.fixtures import REPO_ROOT, align_spec_to_bundle, btc_bundle

# Deterministic pin so evaluate() does not depend on a clean checkout of REPO_ROOT.
_EVAL_SHA = "a" * 40


@pytest.fixture(autouse=True)
def _pin_evaluation_git_sha(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RESEARCH_EVALUATION_GIT_SHA", _EVAL_SHA)
    monkeypatch.delenv("RAILWAY_GIT_COMMIT_SHA", raising=False)


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


def _run_net_pnl(root: Path, run_id: str) -> str:
    entry = ExperimentRegistry(root).show(run_id, verify=True)
    metrics = json.loads((Path(entry.artifact_path) / "metrics.json").read_text(encoding="utf-8"))
    return str(metrics["net_pnl"])


def _clone_run_with_net_pnl(
    root: Path,
    source_run_id: str,
    *,
    new_run_id: str,
    net_pnl: str,
) -> str:
    """Register a cloned complete run with patched ``metrics.json.net_pnl``."""
    registry = ExperimentRegistry(root)
    source = registry.show(source_run_id, verify=True)
    src_dir = Path(source.artifact_path)
    dst_dir = src_dir.parent / new_run_id
    shutil.copytree(src_dir, dst_dir)
    metrics_path = dst_dir / "metrics.json"
    metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
    metrics["net_pnl"] = net_pnl
    # Keep schema 1.1+ accounting identity: gross = net + fees + slippage + funding.
    fees = Decimal(str(metrics.get("fees") or "0"))
    slip = Decimal(str(metrics.get("slippage_costs") or "0"))
    funding = Decimal(str(metrics.get("funding_costs") or "0"))
    metrics["gross_pnl"] = format(Decimal(net_pnl) + fees + slip + funding, "f")
    metrics_path.write_text(json.dumps(metrics, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    checksums = compute_artifact_checksums(dst_dir)
    (dst_dir / "checksums.json").write_text(
        json.dumps(checksums, sort_keys=True, indent=2) + "\n", encoding="utf-8"
    )
    registry.register_complete(
        experiment_id=source.experiment_id,
        run_id=new_run_id,
        attempt_id=f"{new_run_id}_attempt",
        strategy_version=source.strategy_version,
        dataset_version=source.dataset_version,
        cost_model_version=source.cost_model_version,
        benchmark_ref=source.benchmark_ref,
        artifact_path=dst_dir,
        checksums=checksums,
    )
    return new_run_id


def _save_walk_forward_manifest(
    root: Path,
    *,
    base_experiment_id: str,
    base_run_id: str,
    fold_run_ids: list[str] | None = None,
    robustness_id: str = "rob_test_walk_forward",
) -> str:
    fold_run_ids = fold_run_ids or [base_run_id, base_run_id, base_run_id]
    children = tuple(
        RobustnessChildResult(
            child_id=f"fold_{i:02d}",
            label=f"fold_{i:02d}",
            experiment_id=base_experiment_id,
            run_id=rid,
            status="complete",
            net_pnl=_run_net_pnl(root, rid),
        )
        for i, rid in enumerate(fold_run_ids, start=1)
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


def _save_bootstrap_manifest(
    root: Path,
    *,
    base_experiment_id: str,
    base_run_id: str,
    robustness_id: str = "rob_test_bootstrap",
    q05_override: str | None = None,
) -> str:
    entry = ExperimentRegistry(root).show(base_run_id, verify=True)
    config = {
        "block_length": 2,
        "n_simulations": 20,
        "seed": 7,
        "quantiles": [0.05, 0.5, 0.95],
    }
    stats = compute_bootstrap_from_equity_artifact(
        Path(entry.artifact_path),
        block_length=int(config["block_length"]),
        n_simulations=int(config["n_simulations"]),
        seed=int(config["seed"]),
        quantiles=tuple(float(q) for q in config["quantiles"]),
    )
    quantiles = dict(stats.net_pnl_quantiles)
    if q05_override is not None:
        quantiles["q05"] = float(q05_override)
    manifest = RobustnessManifest(
        schema_version=ROBUSTNESS_MANIFEST_SCHEMA_VERSION,
        robustness_id=robustness_id,
        test_type="bootstrap",
        base_experiment_id=base_experiment_id,
        base_run_id=base_run_id,
        dataset_catalog_id=None,
        config=config,
        created_at="2024-01-01T00:00:00.000000Z",
        children=(
            RobustnessChildResult(
                child_id="bootstrap_source",
                label="base run PnL series",
                experiment_id=base_experiment_id,
                run_id=base_run_id,
                status="complete",
            ),
        ),
        bootstrap_result={
            "n_simulations": stats.n_simulations,
            "block_length": stats.block_length,
            "seed": stats.seed,
            "net_pnl_quantiles": quantiles,
            "max_drawdown_quantiles": stats.max_drawdown_quantiles,
            "mean_net_pnl": stats.mean_net_pnl,
            "mean_max_drawdown": stats.mean_max_drawdown,
        },
        summary={"n_children": 1, "n_complete": 1, "n_failed": 0},
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
    assert record.evaluation_code_commit == _EVAL_SHA
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
    )

    evaluator = GateEvaluator(root, repo_root=REPO_ROOT)
    record = evaluator.evaluate(
        run_id=run_id, policy_version="1.0", robustness_run_ids=[robustness_id]
    )

    assert record.robustness_run_ids == (robustness_id,)
    assert f"robustness/{robustness_id}/manifest.json" in record.artifact_checksums
    # All folds share the sealed base-run metrics (net_pnl >= 0 for fixture) → ratio 1.
    assert record.measurements["walk_forward_fold_pass_ratio"] == "1"
    wf_gate = next(g for g in record.gates if g.name == "walk_forward_fold_pass_ratio")
    assert wf_gate.passed is True
    assert record.evaluation_code_commit == _EVAL_SHA


def test_walk_forward_manifest_failing_ratio_fails_gate(tmp_path: Path) -> None:
    root, experiment_id, run_id = _completed_run(tmp_path)
    neg_a = _clone_run_with_net_pnl(root, run_id, new_run_id="run_fold_neg_a", net_pnl="-10")
    neg_b = _clone_run_with_net_pnl(root, run_id, new_run_id="run_fold_neg_b", net_pnl="-20")
    robustness_id = _save_walk_forward_manifest(
        root,
        base_experiment_id=experiment_id,
        base_run_id=run_id,
        fold_run_ids=[neg_a, neg_b, run_id],
    )

    evaluator = GateEvaluator(root, repo_root=REPO_ROOT)
    record = evaluator.evaluate(
        run_id=run_id, policy_version="1.0", robustness_run_ids=[robustness_id]
    )
    wf_gate = next(g for g in record.gates if g.name == "walk_forward_fold_pass_ratio")
    assert record.measurements["walk_forward_fold_pass_ratio"] == (
        "0.3333333333333333333333333333"
    )
    assert wf_gate.passed is False
    assert record.overall_status == "fail"


def test_evaluate_rejects_tampered_manifest_child_net_pnl(tmp_path: Path) -> None:
    """Post-completion tamper of sealed children[].net_pnl must fail closed (P1a)."""
    root, experiment_id, run_id = _completed_run(tmp_path)
    robustness_id = _save_walk_forward_manifest(
        root,
        base_experiment_id=experiment_id,
        base_run_id=run_id,
    )
    path = robustness_manifest_path(root, robustness_id)
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["children"][0]["net_pnl"] = "999999"
    path.write_text(json.dumps(payload, sort_keys=True, indent=2) + "\n", encoding="utf-8")

    evaluator = GateEvaluator(root, repo_root=REPO_ROOT)
    with pytest.raises(GateEvaluationError, match="manifest seal|content hash"):
        evaluator.evaluate(
            run_id=run_id, policy_version="1.0", robustness_run_ids=[robustness_id]
        )


def test_evaluate_rejects_tampered_bootstrap_q05_after_seal(tmp_path: Path) -> None:
    """Post-seal bootstrap_result.q05 tamper must fail closed (P1a / P1b)."""
    root, experiment_id, run_id = _completed_run(tmp_path)
    robustness_id = _save_bootstrap_manifest(
        root, base_experiment_id=experiment_id, base_run_id=run_id
    )
    path = robustness_manifest_path(root, robustness_id)
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["bootstrap_result"]["net_pnl_quantiles"]["q05"] = 999.0
    path.write_text(json.dumps(payload, sort_keys=True, indent=2) + "\n", encoding="utf-8")

    evaluator = GateEvaluator(root, repo_root=REPO_ROOT)
    with pytest.raises(GateEvaluationError, match="manifest seal|content hash"):
        evaluator.evaluate(
            run_id=run_id, policy_version="1.0", robustness_run_ids=[robustness_id]
        )


def test_evaluate_rejects_resealed_bootstrap_q05_disagreement(tmp_path: Path) -> None:
    """Even with a fresh seal, sealed q05 must match equity recompute (P1b)."""
    root, experiment_id, run_id = _completed_run(tmp_path)
    robustness_id = _save_bootstrap_manifest(
        root,
        base_experiment_id=experiment_id,
        base_run_id=run_id,
        q05_override="999",
    )
    evaluator = GateEvaluator(root, repo_root=REPO_ROOT)
    with pytest.raises(GateEvaluationError, match="bootstrap q05"):
        evaluator.evaluate(
            run_id=run_id, policy_version="1.0", robustness_run_ids=[robustness_id]
        )


def test_bootstrap_manifest_binds_recomputed_q05(tmp_path: Path) -> None:
    root, experiment_id, run_id = _completed_run(tmp_path)
    robustness_id = _save_bootstrap_manifest(
        root, base_experiment_id=experiment_id, base_run_id=run_id
    )
    evaluator = GateEvaluator(root, repo_root=REPO_ROOT)
    record = evaluator.evaluate(
        run_id=run_id, policy_version="1.0", robustness_run_ids=[robustness_id]
    )
    assert "bootstrap_q05_net_pnl" in record.measurements
    assert Decimal(record.measurements["bootstrap_q05_net_pnl"]) == Decimal("0")


def test_get_and_list_reject_tampered_evidence_after_evaluate(tmp_path: Path) -> None:
    root, experiment_id, run_id = _completed_run(tmp_path)
    robustness_id = _save_walk_forward_manifest(
        root, base_experiment_id=experiment_id, base_run_id=run_id
    )
    svc = GateService(root, repo_root=REPO_ROOT)
    record = svc.evaluate(
        {"run_id": run_id, "policy_version": "1.0", "robustness_run_ids": [robustness_id]}
    )
    gate_run_id = record["gate_run_id"]
    assert record["evidence_integrity"]["ok"] is True

    # Tamper metrics after evaluate — active get/list must fail closed.
    entry = ExperimentRegistry(root).show(run_id, verify=False)
    metrics_path = Path(entry.artifact_path) / "metrics.json"
    metrics_path.write_bytes(metrics_path.read_bytes() + b"\n")

    with pytest.raises(ResearchWriteError, match="artifact_checksums|checksum|seal"):
        svc.get(gate_run_id)
    with pytest.raises(ResearchWriteError, match="artifact_checksums|checksum|seal"):
        svc.list_all()


def test_get_and_list_reject_tampered_robustness_manifest_after_evaluate(
    tmp_path: Path,
) -> None:
    root, experiment_id, run_id = _completed_run(tmp_path)
    robustness_id = _save_walk_forward_manifest(
        root, base_experiment_id=experiment_id, base_run_id=run_id
    )
    svc = GateService(root, repo_root=REPO_ROOT)
    record = svc.evaluate(
        {"run_id": run_id, "policy_version": "1.0", "robustness_run_ids": [robustness_id]}
    )
    gate_run_id = record["gate_run_id"]

    path = robustness_manifest_path(root, robustness_id)
    tampered = path.read_text(encoding="utf-8").replace("fold_01", "fold_XX", 1)
    path.write_text(tampered, encoding="utf-8")

    with pytest.raises(ResearchWriteError, match="artifact_checksums|seal|manifest"):
        svc.get(gate_run_id)
    with pytest.raises(ResearchWriteError, match="artifact_checksums|seal|manifest"):
        svc.list_all()


def test_invalidated_record_returns_evidence_integrity_flag_on_tamper(
    tmp_path: Path,
) -> None:
    root, _experiment_id, run_id = _completed_run(tmp_path)
    svc = GateService(root, repo_root=REPO_ROOT)
    record = svc.evaluate({"run_id": run_id, "policy_version": "1.0"})
    gate_run_id = record["gate_run_id"]
    svc.invalidate(gate_run_id, {"reason": "fixture", "actor": "test"})

    entry = ExperimentRegistry(root).show(run_id, verify=False)
    metrics_path = Path(entry.artifact_path) / "metrics.json"
    metrics_path.write_bytes(metrics_path.read_bytes() + b"\n")

    body = svc.get(gate_run_id)
    assert body["status"] == "invalidated"
    assert body["evidence_integrity"]["ok"] is False
    assert body["evidence_integrity"]["error"]


def test_evaluate_fails_closed_on_dirty_tree_without_env_pin(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root, _experiment_id, run_id = _completed_run(tmp_path)
    dirty_repo = tmp_path / "dirty_repo"
    dirty_repo.mkdir()
    subprocess.run(["git", "init"], cwd=dirty_repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=dirty_repo,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "test"],
        cwd=dirty_repo,
        check=True,
        capture_output=True,
    )
    (dirty_repo / "README").write_text("x\n", encoding="utf-8")
    subprocess.run(["git", "add", "README"], cwd=dirty_repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "init"],
        cwd=dirty_repo,
        check=True,
        capture_output=True,
    )
    (dirty_repo / "README").write_text("dirty\n", encoding="utf-8")

    monkeypatch.delenv("RESEARCH_EVALUATION_GIT_SHA", raising=False)
    monkeypatch.delenv("RAILWAY_GIT_COMMIT_SHA", raising=False)

    evaluator = GateEvaluator(root, repo_root=dirty_repo)
    with pytest.raises(GateEvaluationError, match="evaluation_code_commit|dirty"):
        evaluator.evaluate(run_id=run_id, policy_version="1.0")


def test_evaluate_missing_robustness_manifest_raises(tmp_path: Path) -> None:
    root, _experiment_id, run_id = _completed_run(tmp_path)
    evaluator = GateEvaluator(root, repo_root=REPO_ROOT)
    with pytest.raises(GateEvaluationError):
        evaluator.evaluate(
            run_id=run_id, policy_version="1.0", robustness_run_ids=["rob_missing"]
        )


def test_evaluate_rejects_cross_run_robustness_evidence(tmp_path: Path) -> None:
    root, experiment_id, run_id = _completed_run(tmp_path)
    foreign_run_id = "run_foreign_not_under_evaluation"
    # Manifest under `root` but pinned to a different base_run_id — exact pin required.
    # Use fold_run_ids pointing at the evaluated run so child seals still resolve;
    # base_run_id mismatch is what must fail closed.
    robustness_id = "rob_cross_run"
    children = tuple(
        RobustnessChildResult(
            child_id=f"fold_{i:02d}",
            label=f"fold_{i:02d}",
            experiment_id=experiment_id,
            run_id=run_id,
            status="complete",
            net_pnl=_run_net_pnl(root, run_id),
        )
        for i in range(1, 4)
    )
    save_robustness_manifest(
        root,
        RobustnessManifest(
            schema_version=ROBUSTNESS_MANIFEST_SCHEMA_VERSION,
            robustness_id=robustness_id,
            test_type="walk_forward",
            base_experiment_id=experiment_id,
            base_run_id=foreign_run_id,
            dataset_catalog_id=None,
            config={},
            created_at="2024-01-01T00:00:00.000000Z",
            children=children,
            bootstrap_result=None,
            summary={"n_children": 3, "n_complete": 3, "n_failed": 0},
        ),
    )
    evaluator = GateEvaluator(root, repo_root=REPO_ROOT)
    with pytest.raises(GateEvaluationError, match="base_run_id|cross-run"):
        evaluator.evaluate(
            run_id=run_id, policy_version="1.0", robustness_run_ids=[robustness_id]
        )


def test_evaluate_rejects_duplicate_test_type_manifests(tmp_path: Path) -> None:
    root, experiment_id, run_id = _completed_run(tmp_path)
    first = _save_walk_forward_manifest(
        root,
        base_experiment_id=experiment_id,
        base_run_id=run_id,
    )
    second_id = "rob_test_walk_forward_dup"
    _save_walk_forward_manifest(
        root,
        base_experiment_id=experiment_id,
        base_run_id=run_id,
        robustness_id=second_id,
    )

    evaluator = GateEvaluator(root, repo_root=REPO_ROOT)
    with pytest.raises(GateEvaluationError, match="duplicate robustness test_type"):
        evaluator.evaluate(
            run_id=run_id,
            policy_version="1.0",
            # Deliberately unsorted — sorting for gate_run_id must not hide the collision.
            robustness_run_ids=[second_id, first],
        )


def test_get_and_list_reject_same_version_policy_content_mismatch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root, _experiment_id, run_id = _completed_run(tmp_path)
    svc = GateService(root, repo_root=REPO_ROOT)
    record = svc.evaluate({"run_id": run_id, "policy_version": "1.0"})
    gate_run_id = record["gate_run_id"]

    # Happy path still works under the unmodified policy.
    assert svc.get(gate_run_id)["gate_run_id"] == gate_run_id
    assert any(i["gate_run_id"] == gate_run_id for i in svc.list_all())

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

    with pytest.raises(ResearchWriteError, match="content hash mismatch"):
        svc.get(gate_run_id)
    with pytest.raises(ResearchWriteError, match="content hash mismatch"):
        svc.list_all()


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
