"""Tests for research compare API (Issue #246).

Reuses ExperimentRegistry.compare semantics only (no second engine, no
P7 ranking). Verifies fail-closed behaviour on incompatible/unknown/
tampered runs, mirroring tests/research/test_research_read_api.py.
"""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from paper_trading.readonly_api import app
from research.api import get_research_service
from research.artifacts import compute_artifact_checksums
from research.service import ResearchReadService

_BASE_EXPERIMENT: dict[str, Any] = {
    "schema_version": "1.0",
    "hypothesis": "smoke compare fixture",
    "strategy_version": "trend-v1.0.0",
    "parameters": {"strategy_id": "trend_v1", "lookback": 20},
    "dataset_manifest_ref": {
        "dataset_id": "ds-fixture",
        "content_hash": "a" * 64,
        "manifest_path": "tests/fixtures/dataset_manifest.json",
    },
    "symbols": ["BTC"],
    "time_range": {
        "start": "2024-01-01T00:00:00.000000Z",
        "end": "2024-03-01T00:00:00.000000Z",
    },
    "starting_capital": "100000",
    "fee_assumption": {
        "entry_fee_rate": "0.0005",
        "exit_fee_rate": "0.0005",
        "model_version": "1.0",
    },
    "slippage_assumption": {"slippage_bps": "5", "model_version": "1.0"},
    "funding_assumption": {
        "enabled": False,
        "assumed_rate": None,
        "model_version": "1.0",
    },
    "cost_scenarios": [],
    "benchmark": "buy_hold_btc",
    "random_seed": 7,
    "expected_artifacts": [],
    "notes": "",
    "owner": "research",
}

_BASE_MANIFEST: dict[str, Any] = {
    "schema_version": "1.0",
    "git_commit": "abc123def",
    "created_at_utc": "2024-06-01T12:00:00.000000Z",
    "status": "complete",
    "dataset_id": "ds-fixture",
    "dataset_content_hash": "a" * 64,
    "strategy_version": "trend-v1.0.0",
    "cost_model_version": "1.0",
    "metrics_schema_version": "1.0",
    "environment_fingerprint": "fingerprint-fixture",
    "identity_hash_algorithm": "sha256",
    "attempt_id": "att-fixture",
}


def _write_run(
    root: Path,
    *,
    experiment_id: str,
    run_id: str,
    status: str = "complete",
    strategy_version: str = "trend-v1.0.0",
    experiment_overrides: dict[str, Any] | None = None,
    manifest_overrides: dict[str, Any] | None = None,
    manifest_identity: tuple[str, str] | None = None,
    net_pnl: str = "10000",
    artifact_path_override: str | None = None,
    checksums_override: dict[str, str] | None = None,
) -> Path:
    """Write one run's artifacts + registry entry.

    ``manifest_identity`` decouples the RunManifest's *embedded*
    experiment_id/run_id from the registry entry's own ids so tests can
    simulate a true reproducibility re-registration (same underlying
    identity, two registry entries) without needing the full
    ``run_experiment`` harness — mirrors ``tests/research/test_compare_semantics.py``'s
    intent, just built from static fixtures.
    """
    run_dir = root / "artifacts" / "research" / experiment_id / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    experiment = deepcopy(_BASE_EXPERIMENT)
    experiment.update(experiment_overrides or {})
    (run_dir / "experiment.json").write_text(
        json.dumps(experiment, sort_keys=True), encoding="utf-8"
    )

    manifest_experiment_id, manifest_run_id = manifest_identity or (
        experiment_id,
        run_id,
    )
    manifest = deepcopy(_BASE_MANIFEST)
    manifest["experiment_id"] = manifest_experiment_id
    manifest["run_id"] = manifest_run_id
    manifest["strategy_version"] = strategy_version
    manifest.update(manifest_overrides or {})
    (run_dir / "run_manifest.json").write_text(
        json.dumps(manifest, sort_keys=True), encoding="utf-8"
    )

    (run_dir / "costs.json").write_text(
        json.dumps({"cost_model_version": "1.0"}, sort_keys=True),
        encoding="utf-8",
    )
    (run_dir / "metrics.json").write_text(
        json.dumps(
            {
                "start_capital": "100000",
                "end_capital": "110000",
                "net_pnl": net_pnl,
                "max_drawdown": "0.12",
                "hit_rate": "0.55",
                "profit_factor": "1.4",
                "closed_trades": 10,
                "status": "ok",
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    (run_dir / "equity.json").write_text(
        json.dumps(
            [
                {"time": "2024-01-01T00:00:00Z", "equity": "100000"},
                {"time": "2024-03-01T00:00:00Z", "equity": "110000"},
            ]
        ),
        encoding="utf-8",
    )

    checksums = (
        checksums_override
        if checksums_override is not None
        else compute_artifact_checksums(run_dir)
    )
    registry = root / "artifacts" / "research" / "registry.jsonl"
    registry.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "experiment_id": experiment_id,
        "run_id": run_id,
        "attempt_id": f"att-{run_id}",
        "status": status,
        "strategy_version": strategy_version,
        "dataset_version": "ds-v1",
        "cost_model_version": "1.0",
        "benchmark_ref": "buy_hold_btc",
        "created_at": "2024-06-01T12:00:00.000000Z",
        "artifact_path": artifact_path_override or str(run_dir),
        "checksums": checksums,
    }
    with registry.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, sort_keys=True) + "\n")
    return run_dir


def _client_for(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("RESEARCH_ARTIFACTS_ROOT", str(tmp_path))
    app.dependency_overrides[get_research_service] = lambda: ResearchReadService(
        tmp_path
    )
    return TestClient(app)


def test_compare_identical_runs_compatible(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Two registry entries sharing one underlying run identity (reproducibility
    re-registration, cf. test_compare_semantics.py::test_compare_compatible_same_artifacts)
    must compare as compatible with no diffs."""
    shared_identity = ("exp-shared", "run-shared")
    _write_run(
        tmp_path,
        experiment_id="exp-a",
        run_id="run-a",
        net_pnl="10000",
        manifest_identity=shared_identity,
    )
    _write_run(
        tmp_path,
        experiment_id="exp-b",
        run_id="run-b",
        net_pnl="20000",
        manifest_identity=shared_identity,
    )
    client = _client_for(tmp_path, monkeypatch)
    try:
        resp = client.get(
            "/api/v1/research/experiments/compare",
            params={"run_a": "run-a", "run_b": "run-b"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["compatible"] is True
        assert body["diffs"] == {}
        assert body["run_a"] == "run-a"
        assert body["run_b"] == "run-b"
        # Metrics must reflect each run's own artifacts, never invented/blended.
        assert body["runs"]["a"]["metrics"]["net_pnl"] == "10000"
        assert body["runs"]["b"]["metrics"]["net_pnl"] == "20000"
        assert len(body["runs"]["a"]["equity"]) == 2
        assert body["runs"]["a"]["integrity"]["ok"] is True
        assert body["runs"]["b"]["integrity"]["ok"] is True
    finally:
        app.dependency_overrides.pop(get_research_service, None)


def test_compare_symbol_mismatch_incompatible(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_run(tmp_path, experiment_id="exp-c", run_id="run-c")
    _write_run(
        tmp_path,
        experiment_id="exp-d",
        run_id="run-d",
        experiment_overrides={"symbols": ["BTC", "ETH"]},
    )
    client = _client_for(tmp_path, monkeypatch)
    try:
        resp = client.get(
            "/api/v1/research/experiments/compare",
            params={"run_a": "run-c", "run_b": "run-d"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["compatible"] is False
        assert "spec.symbols" in body["diffs"]
        assert body["diffs"]["spec.symbols"] == [["BTC"], ["BTC", "ETH"]]
    finally:
        app.dependency_overrides.pop(get_research_service, None)


def test_compare_status_mismatch_incompatible(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_run(tmp_path, experiment_id="exp-e", run_id="run-e", status="complete")
    _write_run(tmp_path, experiment_id="exp-f", run_id="run-f", status="failed")
    client = _client_for(tmp_path, monkeypatch)
    try:
        resp = client.get(
            "/api/v1/research/experiments/compare",
            params={"run_a": "run-e", "run_b": "run-f"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["compatible"] is False
        assert body["diffs"]["status"] == ["complete", "failed"]
    finally:
        app.dependency_overrides.pop(get_research_service, None)


def test_compare_unknown_run_404(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_run(tmp_path, experiment_id="exp-g", run_id="run-g")
    client = _client_for(tmp_path, monkeypatch)
    try:
        resp = client.get(
            "/api/v1/research/experiments/compare",
            params={"run_a": "run-g", "run_b": "run-does-not-exist"},
        )
        assert resp.status_code == 404
    finally:
        app.dependency_overrides.pop(get_research_service, None)


def test_compare_invalid_id_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_run(tmp_path, experiment_id="exp-h", run_id="run-h")
    client = _client_for(tmp_path, monkeypatch)
    try:
        resp = client.get(
            "/api/v1/research/experiments/compare",
            params={"run_a": "run-h", "run_b": "../../etc/passwd"},
        )
        assert resp.status_code == 400
    finally:
        app.dependency_overrides.pop(get_research_service, None)


def test_compare_missing_artifacts_fail_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_run(tmp_path, experiment_id="exp-i", run_id="run-i")
    _write_run(
        tmp_path,
        experiment_id="exp-j",
        run_id="run-j",
        artifact_path_override=str(tmp_path / "artifacts" / "research" / "missing"),
    )
    client = _client_for(tmp_path, monkeypatch)
    try:
        resp = client.get(
            "/api/v1/research/experiments/compare",
            params={"run_a": "run-i", "run_b": "run-j"},
        )
        assert resp.status_code == 409
    finally:
        app.dependency_overrides.pop(get_research_service, None)


def test_compare_tampered_checksum_fail_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_run(tmp_path, experiment_id="exp-k", run_id="run-k")
    _write_run(
        tmp_path,
        experiment_id="exp-l",
        run_id="run-l",
        checksums_override={"metrics.json": "deadbeef"},
    )
    client = _client_for(tmp_path, monkeypatch)
    try:
        resp = client.get(
            "/api/v1/research/experiments/compare",
            params={"run_a": "run-k", "run_b": "run-l"},
        )
        assert resp.status_code == 400
        # Never silently compare tampered artifacts as if trustworthy.
        assert "checksum" in resp.json()["detail"].lower()
    finally:
        app.dependency_overrides.pop(get_research_service, None)


def test_compare_git_commit_mismatch_incompatible(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_run(tmp_path, experiment_id="exp-m", run_id="run-m")
    _write_run(
        tmp_path,
        experiment_id="exp-n",
        run_id="run-n",
        manifest_overrides={"git_commit": "deadbeefdeadbeef"},
    )
    client = _client_for(tmp_path, monkeypatch)
    try:
        resp = client.get(
            "/api/v1/research/experiments/compare",
            params={"run_a": "run-m", "run_b": "run-n"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["compatible"] is False
        assert "manifest.git_commit" in body["diffs"]
    finally:
        app.dependency_overrides.pop(get_research_service, None)
