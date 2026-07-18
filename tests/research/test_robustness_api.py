"""Integration tests for robustness orchestration API (Issue #247 / P4.7b).

Mirrors ``tests/research/test_research_write_api.py`` (Issue #242): same
runner/registry/artifact line, same filesystem job store pattern, same
FastAPI dependency-override fixture style. Public/synthetic BTC fixture data
only — no private Strategy V1 numbers.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from paper_trading.readonly_api import app
from research.api import (
    get_research_service,
    get_research_write_service,
    get_robustness_service,
)
from research.robustness_service import RobustnessOrchestrationService
from research.service import ResearchReadService
from research.write_service import ResearchWriteService

from tests.research.fixtures import align_spec_to_bundle, btc_bundle

REPO_ROOT = Path(__file__).resolve().parents[2]


def _catalog_and_lab_payload(tmp_path: Path) -> tuple[Path, dict[str, object]]:
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
    payload = {
        "strategy_id": "trend_v1",
        "strategy_version": spec.strategy_version,
        "name": "robustness base experiment",
        "notes": "from test",
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
        "slippage_assumption": {"slippage_bps": str(spec.slippage_assumption.slippage_bps)},
        "random_seed": 7,
        "dataset_catalog_id": "fixture-btc",
        "owner": "test",
    }
    return catalog_path, payload


@pytest.fixture
def robustness_client(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[TestClient, str]:
    """A completed base experiment + a client wired to the robustness API."""

    catalog_path, payload = _catalog_and_lab_payload(tmp_path)
    monkeypatch.setenv("RESEARCH_ARTIFACTS_ROOT", str(tmp_path))
    monkeypatch.setenv("RESEARCH_DATASET_CATALOG_PATH", str(catalog_path))
    monkeypatch.setenv("RESEARCH_REPO_ROOT", str(REPO_ROOT))
    monkeypatch.setenv("RESEARCH_ALLOW_DIRTY_GIT", "1")

    def _read() -> ResearchReadService:
        return ResearchReadService(tmp_path)

    def _write() -> ResearchWriteService:
        return ResearchWriteService(tmp_path, repo_root=REPO_ROOT, allow_dirty_git=True)

    def _robustness() -> RobustnessOrchestrationService:
        return RobustnessOrchestrationService(tmp_path, repo_root=REPO_ROOT, allow_dirty_git=True)

    app.dependency_overrides[get_research_service] = _read
    app.dependency_overrides[get_research_write_service] = _write
    app.dependency_overrides[get_robustness_service] = _robustness
    client = TestClient(app)

    created = client.post("/api/v1/research/experiments", json=payload).json()
    base_experiment_id = created["experiment_id"]
    started = client.post(f"/api/v1/research/experiments/{base_experiment_id}/start")
    assert started.status_code == 200, started.text

    deadline = time.time() + 60
    status = "queued"
    while time.time() < deadline:
        status = client.get(
            f"/api/v1/research/experiments/{base_experiment_id}/status"
        ).json()["status"]
        if status in {"completed", "failed"}:
            break
        time.sleep(0.2)
    assert status == "completed", status

    try:
        yield client, base_experiment_id
    finally:
        app.dependency_overrides.pop(get_research_service, None)
        app.dependency_overrides.pop(get_research_write_service, None)
        app.dependency_overrides.pop(get_robustness_service, None)


def _wait_for_robustness_completion(client: TestClient, robustness_id: str) -> dict:
    deadline = time.time() + 90
    body: dict = {}
    while time.time() < deadline:
        body = client.get(f"/api/v1/research/robustness/{robustness_id}/status").json()
        if body["status"] in {"completed", "failed"}:
            break
        time.sleep(0.2)
    assert body.get("status") == "completed", body
    return body


def test_walk_forward_orchestrated_run_completes(
    robustness_client: tuple[TestClient, str],
) -> None:
    client, base_experiment_id = robustness_client
    created = client.post(
        "/api/v1/research/robustness",
        json={
            "base_experiment_id": base_experiment_id,
            "test_type": "walk_forward",
            "dataset_catalog_id": "fixture-btc",
            "config": {"n_folds": 2, "embargo_days": 0, "feature_warmup_monthly_bars": 1},
        },
    )
    assert created.status_code == 200, created.text
    robustness_id = created.json()["robustness_id"]
    assert robustness_id.startswith("rob_")

    started = client.post(f"/api/v1/research/robustness/{robustness_id}/start")
    assert started.status_code == 200, started.text

    _wait_for_robustness_completion(client, robustness_id)

    detail = client.get(f"/api/v1/research/robustness/{robustness_id}").json()
    manifest = detail["manifest"]
    assert manifest["test_type"] == "walk_forward"
    assert manifest["summary"]["n_children"] == 2
    assert manifest["summary"]["n_failed"] == 0
    child_ids = [c["child_id"] for c in manifest["children"]]
    assert child_ids == ["fold_01", "fold_02"]
    for child in manifest["children"]:
        assert child["status"] == "complete"
        assert child["experiment_id"] is not None
        assert child["run_id"] is not None

    listed = client.get("/api/v1/research/robustness").json()["items"]
    assert any(j["robustness_id"] == robustness_id for j in listed)


def test_cost_stress_orchestrated_run_completes(
    robustness_client: tuple[TestClient, str],
) -> None:
    client, base_experiment_id = robustness_client
    created = client.post(
        "/api/v1/research/robustness",
        json={
            "base_experiment_id": base_experiment_id,
            "test_type": "cost_stress",
            "dataset_catalog_id": "fixture-btc",
        },
    )
    assert created.status_code == 200, created.text
    robustness_id = created.json()["robustness_id"]
    client.post(f"/api/v1/research/robustness/{robustness_id}/start")
    _wait_for_robustness_completion(client, robustness_id)

    manifest = client.get(f"/api/v1/research/robustness/{robustness_id}").json()["manifest"]
    assert manifest["summary"]["n_children"] == 6
    assert manifest["summary"]["n_failed"] == 0
    assert {c["child_id"] for c in manifest["children"]} == {
        "base",
        "fee_x2",
        "slippage_x2",
        "funding_stress",
        "combined_elevated",
        "combined_extreme",
    }


def test_parameter_stability_orchestrated_run_completes(
    robustness_client: tuple[TestClient, str],
) -> None:
    client, base_experiment_id = robustness_client
    created = client.post(
        "/api/v1/research/robustness",
        json={
            "base_experiment_id": base_experiment_id,
            "test_type": "parameter_stability",
            "dataset_catalog_id": "fixture-btc",
            "config": {
                "int_deltas": {"atr_period": [-1, 1]},
                "decimal_relative_steps": {"_unused": ["0.1"]},
            },
        },
    )
    assert created.status_code == 200, created.text
    robustness_id = created.json()["robustness_id"]
    client.post(f"/api/v1/research/robustness/{robustness_id}/start")
    _wait_for_robustness_completion(client, robustness_id)

    manifest = client.get(f"/api/v1/research/robustness/{robustness_id}").json()["manifest"]
    assert manifest["summary"]["n_children"] == 3
    assert manifest["children"][0]["child_id"] == "frozen"


def test_bootstrap_orchestrated_run_completes(
    robustness_client: tuple[TestClient, str],
) -> None:
    client, base_experiment_id = robustness_client
    created = client.post(
        "/api/v1/research/robustness",
        json={
            "base_experiment_id": base_experiment_id,
            "test_type": "bootstrap",
            "config": {"block_length": 2, "n_simulations": 50, "seed": 42},
        },
    )
    assert created.status_code == 200, created.text
    robustness_id = created.json()["robustness_id"]
    client.post(f"/api/v1/research/robustness/{robustness_id}/start")
    _wait_for_robustness_completion(client, robustness_id)

    manifest = client.get(f"/api/v1/research/robustness/{robustness_id}").json()["manifest"]
    assert manifest["test_type"] == "bootstrap"
    assert manifest["bootstrap_result"] is not None
    assert set(manifest["bootstrap_result"]["net_pnl_quantiles"]) == {"q05", "q50", "q95"}
    assert manifest["children"][0]["experiment_id"] == base_experiment_id


def test_create_rejects_unknown_test_type(
    robustness_client: tuple[TestClient, str],
) -> None:
    client, base_experiment_id = robustness_client
    resp = client.post(
        "/api/v1/research/robustness",
        json={"base_experiment_id": base_experiment_id, "test_type": "nope"},
    )
    assert resp.status_code == 422
    assert "test_type" in resp.json()["detail"]["fields"]


def test_create_rejects_missing_base_experiment(
    robustness_client: tuple[TestClient, str],
) -> None:
    client, _ = robustness_client
    resp = client.post(
        "/api/v1/research/robustness",
        json={"base_experiment_id": "exp_missing", "test_type": "bootstrap", "config": {}},
    )
    assert resp.status_code == 422
    assert "base_experiment_id" in resp.json()["detail"]["fields"]


def test_create_persists_base_run_id_on_job(
    robustness_client: tuple[TestClient, str],
) -> None:
    client, base_experiment_id = robustness_client
    status = client.get(f"/api/v1/research/experiments/{base_experiment_id}/status").json()
    run_a = status["run_id"]
    assert run_a

    created = client.post(
        "/api/v1/research/robustness",
        json={
            "base_experiment_id": base_experiment_id,
            "test_type": "bootstrap",
            "config": {"block_length": 2, "n_simulations": 10, "seed": 9},
        },
    ).json()
    assert created["base_run_id"] == run_a
    assert created["job"]["base_run_id"] == run_a

    status_body = client.get(
        f"/api/v1/research/robustness/{created['robustness_id']}/status"
    ).json()
    assert status_body["base_run_id"] == run_a
    assert status_body["job"]["base_run_id"] == run_a


def test_job_honors_pinned_base_run_despite_newer_complete_run(
    robustness_client: tuple[TestClient, str],
    tmp_path: Path,
) -> None:
    """Create with run A, register newer complete run B, start → still uses A."""
    import shutil

    from research.artifacts import load_checksums
    from research.registry import ExperimentRegistry

    client, base_experiment_id = robustness_client
    status = client.get(f"/api/v1/research/experiments/{base_experiment_id}/status").json()
    run_a = status["run_id"]
    assert run_a

    created = client.post(
        "/api/v1/research/robustness",
        json={
            "base_experiment_id": base_experiment_id,
            "test_type": "bootstrap",
            "config": {"block_length": 2, "n_simulations": 25, "seed": 11},
        },
    ).json()
    robustness_id = created["robustness_id"]
    assert created["base_run_id"] == run_a
    assert created["job"]["base_run_id"] == run_a

    # Register a newer complete run B for the same experiment (would win
    # ``_latest_complete_entry`` without a pin).
    registry = ExperimentRegistry(tmp_path)
    entry_a = registry.show(run_a, verify=True)
    run_b = "run_newer_than_pinned_base"
    attempt_b = "att_newer_than_pinned_base"
    artifact_b = Path(entry_a.artifact_path).parent / run_b
    shutil.copytree(entry_a.artifact_path, artifact_b)
    registry.register_complete(
        experiment_id=base_experiment_id,
        run_id=run_b,
        attempt_id=attempt_b,
        strategy_version=entry_a.strategy_version,
        dataset_version=entry_a.dataset_version,
        cost_model_version=entry_a.cost_model_version,
        benchmark_ref=entry_a.benchmark_ref,
        artifact_path=artifact_b,
        checksums=load_checksums(artifact_b),
    )
    latest = [
        e
        for e in registry.list_entries()
        if e.experiment_id == base_experiment_id and e.status == "complete"
    ][-1]
    assert latest.run_id == run_b

    client.post(f"/api/v1/research/robustness/{robustness_id}/start")
    _wait_for_robustness_completion(client, robustness_id)

    manifest = client.get(f"/api/v1/research/robustness/{robustness_id}").json()["manifest"]
    assert manifest["base_run_id"] == run_a
    assert manifest["children"][0]["run_id"] == run_a


def test_create_is_idempotent_for_identical_config(
    robustness_client: tuple[TestClient, str],
) -> None:
    client, base_experiment_id = robustness_client
    payload = {
        "base_experiment_id": base_experiment_id,
        "test_type": "bootstrap",
        "config": {"block_length": 2, "n_simulations": 20, "seed": 1},
    }
    first = client.post("/api/v1/research/robustness", json=payload).json()
    robustness_id = first["robustness_id"]
    assert first["already_exists"] is False
    client.post(f"/api/v1/research/robustness/{robustness_id}/start")
    _wait_for_robustness_completion(client, robustness_id)

    second = client.post("/api/v1/research/robustness", json=payload)
    assert second.status_code == 200
    body = second.json()
    assert body["robustness_id"] == robustness_id
    assert body["already_exists"] is True
    assert body["status"] == "completed"


def test_double_start_is_rejected(robustness_client: tuple[TestClient, str]) -> None:
    client, base_experiment_id = robustness_client
    created = client.post(
        "/api/v1/research/robustness",
        json={
            "base_experiment_id": base_experiment_id,
            "test_type": "bootstrap",
            "config": {"block_length": 2, "n_simulations": 10, "seed": 3},
        },
    ).json()
    robustness_id = created["robustness_id"]
    first_start = client.post(f"/api/v1/research/robustness/{robustness_id}/start")
    assert first_start.status_code == 200
    second_start = client.post(f"/api/v1/research/robustness/{robustness_id}/start")
    assert second_start.status_code == 409
    _wait_for_robustness_completion(client, robustness_id)


def test_unknown_robustness_status_404(robustness_client: tuple[TestClient, str]) -> None:
    client, _ = robustness_client
    resp = client.get("/api/v1/research/robustness/rob_missing/status")
    assert resp.status_code == 404


def test_robustness_post_allowed_paper_post_blocked(
    robustness_client: tuple[TestClient, str],
) -> None:
    client, base_experiment_id = robustness_client
    assert client.post("/api/v1/status").status_code == 405
    resp = client.post(
        "/api/v1/research/robustness",
        json={
            "base_experiment_id": base_experiment_id,
            "test_type": "bootstrap",
            "config": {},
        },
    )
    assert resp.status_code == 200
