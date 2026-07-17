"""Semantic registry compare coverage (#167 / #171)."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from copy import deepcopy
from pathlib import Path
from typing import Any

from research.artifacts import load_checksums
from research.registry import ExperimentRegistry
from research.runner import RunRequest, run_experiment

from tests.research.fixtures import REPO_ROOT, align_spec_to_bundle, btc_bundle


def _compute_checksums(run_dir: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    for path in sorted(run_dir.rglob("*")):
        if path.is_file() and path.name != "checksums.json":
            rel = path.relative_to(run_dir).as_posix()
            out[rel] = hashlib.sha256(path.read_bytes()).hexdigest()
    return out


def _register(tmp_path: Path, *, label: str):
    bundle = btc_bundle()
    label_dir = tmp_path / label
    label_dir.mkdir(parents=True, exist_ok=True)
    spec = align_spec_to_bundle(label_dir, bundle, price_note=label)
    root = tmp_path / f"root-{label}"
    outcome = run_experiment(
        RunRequest(
            spec=spec,
            bundle=bundle,
            artifacts_root=root,
            repo_root=REPO_ROOT,
                    allow_dirty_git=True,
        )
    )
    assert outcome.status == "complete", outcome.error
    assert outcome.artifact_path is not None
    registry = ExperimentRegistry(root)
    registry.register_complete(
        experiment_id=outcome.experiment_id,
        run_id=outcome.run_id,
        attempt_id=outcome.attempt_id,
        strategy_version=spec.strategy_version,
        dataset_version=spec.dataset_manifest_ref.dataset_id,
        cost_model_version="1.0",
        benchmark_ref=spec.benchmark,
        artifact_path=outcome.artifact_path,
        checksums=load_checksums(outcome.artifact_path),
    )
    return registry, outcome, spec


def _clone_artifacts(src: Path, dest: Path) -> dict[str, str]:
    dest.mkdir(parents=True, exist_ok=True)
    for name in src.iterdir():
        if name.is_file():
            (dest / name.name).write_bytes(name.read_bytes())
    seal = _compute_checksums(dest)
    (dest / "checksums.json").write_text(
        json.dumps(seal, sort_keys=True) + "\n", encoding="utf-8"
    )
    return _compute_checksums(dest)


def _append_twin(
    registry: ExperimentRegistry,
    *,
    outcome: Any,
    spec: Any,
    run_id: str,
    artifact_path: Path,
    checksums: dict[str, str],
) -> None:
    registry._append(  # noqa: SLF001
        {
            "experiment_id": outcome.experiment_id,
            "run_id": run_id,
            "attempt_id": f"att_{run_id}",
            "status": "complete",
            "strategy_version": spec.strategy_version,
            "dataset_version": spec.dataset_manifest_ref.dataset_id,
            "cost_model_version": "1.0",
            "benchmark_ref": spec.benchmark,
            "created_at": "2026-01-01T00:00:00.000000Z",
            "artifact_path": str(artifact_path),
            "checksums": checksums,
        }
    )


def _mutate_experiment(
    twin: Path,
    mutator: Callable[[dict[str, Any]], None],
) -> dict[str, str]:
    exp = json.loads((twin / "experiment.json").read_text(encoding="utf-8"))
    mutator(exp)
    (twin / "experiment.json").write_text(
        json.dumps(exp, sort_keys=True) + "\n", encoding="utf-8"
    )
    seal = _compute_checksums(twin)
    (twin / "checksums.json").write_text(
        json.dumps(seal, sort_keys=True) + "\n", encoding="utf-8"
    )
    return _compute_checksums(twin)


def test_compare_compatible_same_artifacts(tmp_path: Path) -> None:
    registry, outcome, spec = _register(tmp_path, label="same")
    _append_twin(
        registry,
        outcome=outcome,
        spec=spec,
        run_id="run_clone_compat",
        artifact_path=outcome.artifact_path,  # type: ignore[arg-type]
        checksums=load_checksums(outcome.artifact_path),  # type: ignore[arg-type]
    )
    result = registry.compare(outcome.run_id, "run_clone_compat")
    assert result["compatible"] is True
    assert result["diffs"] == {}


def test_compare_parameter_mismatch(tmp_path: Path) -> None:
    registry, outcome, spec = _register(tmp_path, label="params")
    twin = tmp_path / "twin-params"
    assert outcome.artifact_path is not None
    _clone_artifacts(outcome.artifact_path, twin)

    def mutate(exp: dict[str, Any]) -> None:
        exp["parameters"] = deepcopy(exp["parameters"])
        exp["parameters"]["breakout_lookback"] = 99

    seal = _mutate_experiment(twin, mutate)
    _append_twin(
        registry,
        outcome=outcome,
        spec=spec,
        run_id="run_params_diff",
        artifact_path=twin,
        checksums=seal,
    )
    result = registry.compare(outcome.run_id, "run_params_diff")
    assert result["compatible"] is False
    assert "spec.parameters" in result["diffs"]


def test_compare_git_commit_mismatch(tmp_path: Path) -> None:
    registry, outcome, spec = _register(tmp_path, label="git")
    twin = tmp_path / "twin-git"
    assert outcome.artifact_path is not None
    _clone_artifacts(outcome.artifact_path, twin)
    man = json.loads((twin / "run_manifest.json").read_text(encoding="utf-8"))
    man["git_commit"] = "deadbeefdeadbeefdeadbeefdeadbeefdeadbeef"
    (twin / "run_manifest.json").write_text(
        json.dumps(man, sort_keys=True) + "\n", encoding="utf-8"
    )
    seal = _compute_checksums(twin)
    (twin / "checksums.json").write_text(
        json.dumps(seal, sort_keys=True) + "\n", encoding="utf-8"
    )
    seal = _compute_checksums(twin)
    _append_twin(
        registry,
        outcome=outcome,
        spec=spec,
        run_id="run_git_diff",
        artifact_path=twin,
        checksums=seal,
    )
    result = registry.compare(outcome.run_id, "run_git_diff")
    assert result["compatible"] is False
    assert "manifest.git_commit" in result["diffs"]


def test_compare_dataset_hash_mismatch(tmp_path: Path) -> None:
    registry, outcome, spec = _register(tmp_path, label="dhash")
    twin = tmp_path / "twin-hash"
    assert outcome.artifact_path is not None
    _clone_artifacts(outcome.artifact_path, twin)

    def mutate(exp: dict[str, Any]) -> None:
        exp["dataset_manifest_ref"] = deepcopy(exp["dataset_manifest_ref"])
        exp["dataset_manifest_ref"]["content_hash"] = "b" * 64

    seal = _mutate_experiment(twin, mutate)
    _append_twin(
        registry,
        outcome=outcome,
        spec=spec,
        run_id="run_hash_diff",
        artifact_path=twin,
        checksums=seal,
    )
    result = registry.compare(outcome.run_id, "run_hash_diff")
    assert result["compatible"] is False
    assert "spec.dataset_manifest_ref" in result["diffs"]


def test_compare_symbols_mismatch(tmp_path: Path) -> None:
    registry, outcome, spec = _register(tmp_path, label="symbols")
    twin = tmp_path / "twin-symbols"
    assert outcome.artifact_path is not None
    _clone_artifacts(outcome.artifact_path, twin)

    def mutate(exp: dict[str, Any]) -> None:
        exp["symbols"] = ["BTC", "ETH"]

    seal = _mutate_experiment(twin, mutate)
    _append_twin(
        registry,
        outcome=outcome,
        spec=spec,
        run_id="run_symbols_diff",
        artifact_path=twin,
        checksums=seal,
    )
    result = registry.compare(outcome.run_id, "run_symbols_diff")
    assert result["compatible"] is False
    assert "spec.symbols" in result["diffs"]


def test_compare_starting_capital_and_fees(tmp_path: Path) -> None:
    registry, outcome, spec = _register(tmp_path, label="capital")
    twin = tmp_path / "twin-capital"
    assert outcome.artifact_path is not None
    _clone_artifacts(outcome.artifact_path, twin)

    def mutate(exp: dict[str, Any]) -> None:
        exp["starting_capital"] = "99999"
        exp["fee_assumption"] = deepcopy(exp["fee_assumption"])
        exp["fee_assumption"]["entry_fee_rate"] = "0.05"
        exp["slippage_assumption"] = deepcopy(exp["slippage_assumption"])
        exp["slippage_assumption"]["slippage_bps"] = "50"
        exp["funding_assumption"] = deepcopy(exp["funding_assumption"])
        exp["funding_assumption"]["enabled"] = True
        exp["funding_assumption"]["assumed_rate"] = "0.001"
        exp["random_seed"] = 7

    seal = _mutate_experiment(twin, mutate)
    _append_twin(
        registry,
        outcome=outcome,
        spec=spec,
        run_id="run_capital_diff",
        artifact_path=twin,
        checksums=seal,
    )
    result = registry.compare(outcome.run_id, "run_capital_diff")
    assert result["compatible"] is False
    for key in (
        "spec.starting_capital",
        "spec.fee_assumption",
        "spec.slippage_assumption",
        "spec.funding_assumption",
        "spec.random_seed",
    ):
        assert key in result["diffs"], key


def test_compare_time_range_mismatch(tmp_path: Path) -> None:
    registry, outcome, spec = _register(tmp_path, label="trange")
    twin = tmp_path / "twin-trange"
    assert outcome.artifact_path is not None
    _clone_artifacts(outcome.artifact_path, twin)

    def mutate(exp: dict[str, Any]) -> None:
        exp["time_range"] = deepcopy(exp["time_range"])
        exp["time_range"]["end"] = "2024-01-15T23:59:59.000000Z"

    seal = _mutate_experiment(twin, mutate)
    _append_twin(
        registry,
        outcome=outcome,
        spec=spec,
        run_id="run_trange_diff",
        artifact_path=twin,
        checksums=seal,
    )
    result = registry.compare(outcome.run_id, "run_trange_diff")
    assert result["compatible"] is False
    assert "spec.time_range" in result["diffs"]


def test_compare_cost_scenarios_mismatch(tmp_path: Path) -> None:
    registry, outcome, spec = _register(tmp_path, label="scenarios")
    twin = tmp_path / "twin-scenarios"
    assert outcome.artifact_path is not None
    _clone_artifacts(outcome.artifact_path, twin)

    def mutate(exp: dict[str, Any]) -> None:
        exp["cost_scenarios"] = [
            {
                "name": "stress_high_fee",
                "fee_assumption": {
                    "entry_fee_rate": "0.01",
                    "exit_fee_rate": "0.01",
                    "model_version": "1.0",
                },
                "slippage_assumption": {
                    "slippage_bps": "10",
                    "model_version": "1.0",
                },
                "funding_assumption": {
                    "enabled": False,
                    "assumed_rate": None,
                    "model_version": "1.0",
                },
            }
        ]

    seal = _mutate_experiment(twin, mutate)
    _append_twin(
        registry,
        outcome=outcome,
        spec=spec,
        run_id="run_scenarios_diff",
        artifact_path=twin,
        checksums=seal,
    )
    result = registry.compare(outcome.run_id, "run_scenarios_diff")
    assert result["compatible"] is False
    assert "spec.cost_scenarios" in result["diffs"]


def test_compare_invalidated_incompatible(tmp_path: Path) -> None:
    registry, outcome, _spec = _register(tmp_path, label="inv")
    inv_path = registry.invalidate(outcome.run_id, reason="test", actor="test")
    assert inv_path.is_file()
    inv = registry.show(outcome.run_id, verify=False)
    assert inv.status == "invalidated"
    registry._append(  # noqa: SLF001
        {
            "experiment_id": outcome.experiment_id,
            "run_id": "run_still_complete",
            "attempt_id": "att_c",
            "status": "complete",
            "strategy_version": inv.strategy_version,
            "dataset_version": inv.dataset_version,
            "cost_model_version": inv.cost_model_version,
            "benchmark_ref": inv.benchmark_ref,
            "created_at": "2026-01-01T00:00:00.000000Z",
            "artifact_path": inv.artifact_path,
            "checksums": inv.checksums,
        }
    )
    result = registry.compare(outcome.run_id, "run_still_complete")
    assert result["compatible"] is False
    assert "status" in result["diffs"]
