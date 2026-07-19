"""Tests for read-only scorecard detail API (#350)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from research.gate_evaluator import GateEvaluator
from research.registry import ExperimentRegistry
from research.robustness import (
    ROBUSTNESS_MANIFEST_SCHEMA_VERSION,
    RobustnessChildResult,
    RobustnessManifest,
    save_robustness_manifest,
)
from research.scorecard_detail import NOT_AVAILABLE, assemble_scorecard_detail
from research.scorecard_evaluator import ScorecardEvaluator, ScorecardResultStore
from research.scorecard_service import ScorecardService

from tests.research import test_gate_evaluator as te


@pytest.fixture(autouse=True)
def _pin_evaluation_git_sha(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RESEARCH_EVALUATION_GIT_SHA", "a" * 40)
    monkeypatch.delenv("RAILWAY_GIT_COMMIT_SHA", raising=False)


def _evaluator(root: Path) -> ScorecardEvaluator:
    return ScorecardEvaluator(root, repo_root=te._evaluation_image_root(root))


def _save_cost_stress_manifest(
    root: Path,
    *,
    base_experiment_id: str,
    base_run_id: str,
    robustness_id: str = "rob_test_cost_stress",
) -> str:
    children = (
        RobustnessChildResult(
            child_id="base",
            label="base",
            experiment_id=base_experiment_id,
            run_id=base_run_id,
            status="complete",
            net_pnl=te._run_net_pnl(root, base_run_id),
        ),
        RobustnessChildResult(
            child_id="combined_elevated",
            label="combined_elevated",
            experiment_id=base_experiment_id,
            run_id=base_run_id,
            status="complete",
            net_pnl="1.23",
        ),
    )
    manifest = RobustnessManifest(
        schema_version=ROBUSTNESS_MANIFEST_SCHEMA_VERSION,
        robustness_id=robustness_id,
        test_type="cost_stress",
        base_experiment_id=base_experiment_id,
        base_run_id=base_run_id,
        dataset_catalog_id=None,
        config={},
        created_at="2024-01-01T00:00:00.000000Z",
        children=children,
        bootstrap_result=None,
        summary={"n_children": 2, "n_complete": 2, "n_failed": 0},
    )
    _path, digest = save_robustness_manifest(root, manifest)
    te._seal_completed_robustness_job(
        root,
        robustness_id=robustness_id,
        base_experiment_id=base_experiment_id,
        base_run_id=base_run_id,
        test_type="cost_stress",
        digest=digest,
    )
    return robustness_id


def test_detail_regime_rows_join_sealed_metrics(tmp_path: Path) -> None:
    root, _experiment_id, run_id = te._completed_run(tmp_path)
    record = _evaluator(root).evaluate(run_id=run_id, policy_version="1.0")
    detail = assemble_scorecard_detail(root, record)

    assert detail["scorecard_id"] == record.scorecard_id
    assert detail["decision_binding"] is False
    assert detail["auto_promotion"] is False
    assert detail["promotion_action"] == "none"
    assert detail["missing_data_semantics"]["token"] == NOT_AVAILABLE

    entry = ExperimentRegistry(root).show(run_id, verify=True)
    metrics = json.loads(
        (Path(entry.artifact_path) / "regime_metrics.json").read_text(encoding="utf-8")
    )
    sealed_cells = [r["cell_id"] for r in metrics["regimes"] if r.get("cell_id")]
    detail_cells = [r["cell_id"] for r in detail["regime_rows"]]
    assert detail_cells == sealed_cells
    assert detail["regime_rows"], "expected at least one regime row from fixture"

    by_cell = {r["cell_id"]: r for r in detail["regime_rows"]}
    for sealed in metrics["regimes"]:
        cell = sealed["cell_id"]
        row = by_cell[cell]
        assert row["trades"]["value"] == sealed["closed_trades"]
        assert row["net_pnl"]["value"] == sealed["net_pnl"]
        assert row["costs"]["status"] == "OK"
        assert row["costs"]["value"] == sealed["costs"]
        # Never invent zeros for missing optional fields.
        if sealed.get("benchmark_delta") in (None, NOT_AVAILABLE):
            assert row["benchmark_delta"]["status"] == NOT_AVAILABLE
            assert row["benchmark_delta"]["value"] is None
        assert "quality" in row
        assert "confidence" in row
        assert "behaviour" in row
        assert row["confidence"]["scope"] == "scorecard_overall"

    assert detail["transition_risk"]["status"] == "OK"
    assert detail["cost_stress"]["status"] == NOT_AVAILABLE
    assert detail["gate_failures"][0]["reason"] == "no_bound_gate_run"
    assert any(r["name"] == "regime_metrics.json" for r in detail["raw_artifact_refs"])
    assert detail["evidence_inputs"]["run_id"] == run_id
    assert detail["evidence_inputs"]["promotion_action"] == "none"


def test_detail_cost_stress_from_pinned_robustness(tmp_path: Path) -> None:
    root, experiment_id, run_id = te._completed_run(tmp_path)
    rob_id = _save_cost_stress_manifest(
        root, base_experiment_id=experiment_id, base_run_id=run_id
    )
    record = _evaluator(root).evaluate(
        run_id=run_id, policy_version="1.0", robustness_run_ids=[rob_id]
    )
    detail = assemble_scorecard_detail(root, record)
    assert detail["cost_stress"]["status"] == "OK"
    assert detail["cost_stress"]["robustness_run_id"] == rob_id
    child = detail["cost_stress"]["combined_elevated_child"]
    assert child is not None
    assert child["label"] == "combined_elevated"
    assert child["net_pnl"] == "1.23"


def test_detail_gate_failures_no_promotion(tmp_path: Path) -> None:
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
    record = _evaluator(root).evaluate(
        run_id=run_id,
        policy_version="1.0",
        gate_run_id=gate.gate_run_id,
        robustness_run_ids=[robustness_id],
    )
    detail = assemble_scorecard_detail(root, record)
    assert detail["decision_binding"] is False
    assert detail["auto_promotion"] is False
    assert detail["promotion_action"] == "none"
    assert detail["gate_failures"]
    assert all(f.get("outcome") != "PASS" for f in detail["gate_failures"])
    # Cost-stress still NA when only walk-forward is pinned.
    assert detail["cost_stress"]["status"] == NOT_AVAILABLE


def test_detail_service_and_summary_unchanged(tmp_path: Path) -> None:
    root, _experiment_id, run_id = te._completed_run(tmp_path)
    svc = ScorecardService(root, repo_root=te._evaluation_image_root(root))
    summary = svc.evaluate({"run_id": run_id, "policy_version": "1.0"})
    sid = summary["scorecard_id"]
    got_summary = svc.get(sid)
    detail = svc.get_detail(sid)
    assert "regime_rows" not in got_summary
    assert "regime_rows" in detail
    assert detail["scorecard_id"] == sid
    assert detail["evidence_integrity"]["ok"] is True
    assert got_summary["scorecard_id"] == sid


def test_detail_tampered_active_fail_closed(tmp_path: Path) -> None:
    root, _experiment_id, run_id = te._completed_run(tmp_path)
    svc = ScorecardService(root, repo_root=te._evaluation_image_root(root))
    record = svc.evaluate({"run_id": run_id, "policy_version": "1.0"})
    sid = record["scorecard_id"]
    lines = ScorecardResultStore(root).path.read_text(encoding="utf-8").strip().splitlines()
    payload = json.loads(lines[0])
    payload["global_profile"] = {**payload["global_profile"], "tampered": True}
    ScorecardResultStore(root).path.write_text(
        json.dumps(payload, sort_keys=True) + "\n", encoding="utf-8"
    )
    with pytest.raises(Exception, match="hash|mismatch|untrusted"):
        svc.get_detail(sid)
