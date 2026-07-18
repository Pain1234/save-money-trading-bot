"""Integration tests for the gate evaluation API (Issue #248 / P4.7c).

Mirrors ``tests/research/test_robustness_api.py`` (#247): same FastAPI
dependency-override fixture style, public/synthetic BTC fixture data only —
no private Strategy V1 numbers, no live/paper promotion anywhere in this
surface.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from paper_trading.readonly_api import app
from research.api import (
    get_gate_service,
    get_research_service,
    get_research_write_service,
    get_robustness_service,
)
from research.gate_service import GateService
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
        "name": "gate base experiment",
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
def gate_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[TestClient, str]:
    """A completed base experiment + a client wired to the gate API."""

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

    def _gate() -> GateService:
        return GateService(tmp_path, repo_root=REPO_ROOT)

    app.dependency_overrides[get_research_service] = _read
    app.dependency_overrides[get_research_write_service] = _write
    app.dependency_overrides[get_robustness_service] = _robustness
    app.dependency_overrides[get_gate_service] = _gate
    client = TestClient(app)

    created = client.post("/api/v1/research/experiments", json=payload).json()
    base_experiment_id = created["experiment_id"]
    started = client.post(f"/api/v1/research/experiments/{base_experiment_id}/start")
    assert started.status_code == 200, started.text

    deadline = time.time() + 60
    status = "queued"
    while time.time() < deadline:
        status_body = client.get(
            f"/api/v1/research/experiments/{base_experiment_id}/status"
        ).json()
        status = status_body["status"]
        if status in {"completed", "failed"}:
            run_id = status_body["job"].get("run_id") or status_body.get("run_id")
            break
        time.sleep(0.2)
    assert status == "completed", status

    detail = client.get(f"/api/v1/research/experiments/{base_experiment_id}").json()
    run_id = detail["summary"]["run_id"]
    assert run_id, detail

    try:
        yield client, run_id
    finally:
        app.dependency_overrides.pop(get_research_service, None)
        app.dependency_overrides.pop(get_research_write_service, None)
        app.dependency_overrides.pop(get_robustness_service, None)
        app.dependency_overrides.pop(get_gate_service, None)


def test_list_gate_policies_exposes_content_hash(gate_client: tuple[TestClient, str]) -> None:
    client, _run_id = gate_client
    resp = client.get("/api/v1/research/gate-policies")
    assert resp.status_code == 200, resp.text
    items = resp.json()["items"]
    assert any(item["version"] == "1.0" and len(item["content_hash"]) == 64 for item in items)


def test_evaluate_gate_binds_evidence(gate_client: tuple[TestClient, str]) -> None:
    client, run_id = gate_client
    resp = client.post(
        "/api/v1/research/gates/evaluate",
        json={"run_id": run_id, "policy_version": "1.0"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["run_id"] == run_id
    assert body["policy_version"] == "1.0"
    assert len(body["policy_content_hash"]) == 64
    assert body["run_code_commit"]
    assert body["evaluation_code_commit"]
    assert body["dataset_id"]
    assert len(body["dataset_content_hash"]) == 64
    assert body["artifact_checksums"]
    assert body["promotion_action"] == "none"
    assert body["status"] == "active"
    assert body["overall_status"] in {"pass", "fail"}
    assert body["gate_run_id"].startswith("gate_")


def test_evaluate_gate_is_idempotent(gate_client: tuple[TestClient, str]) -> None:
    client, run_id = gate_client
    payload = {"run_id": run_id, "policy_version": "1.0"}
    first = client.post("/api/v1/research/gates/evaluate", json=payload).json()
    second = client.post("/api/v1/research/gates/evaluate", json=payload).json()
    assert first["gate_run_id"] == second["gate_run_id"]

    listed = client.get("/api/v1/research/gates").json()["items"]
    matching = [i for i in listed if i["gate_run_id"] == first["gate_run_id"]]
    assert len(matching) == 1


def test_evaluate_gate_rejects_missing_run_id(gate_client: tuple[TestClient, str]) -> None:
    client, _run_id = gate_client
    resp = client.post("/api/v1/research/gates/evaluate", json={"policy_version": "1.0"})
    assert resp.status_code == 422
    assert "run_id" in resp.json()["detail"]["fields"]


def test_evaluate_gate_rejects_unknown_policy_version(gate_client: tuple[TestClient, str]) -> None:
    client, run_id = gate_client
    resp = client.post(
        "/api/v1/research/gates/evaluate",
        json={"run_id": run_id, "policy_version": "999.0"},
    )
    assert resp.status_code == 422
    assert "policy_version" in resp.json()["detail"]["fields"]


def test_evaluate_gate_rejects_unknown_run_id(gate_client: tuple[TestClient, str]) -> None:
    client, _run_id = gate_client
    resp = client.post(
        "/api/v1/research/gates/evaluate",
        json={"run_id": "run_missing", "policy_version": "1.0"},
    )
    assert resp.status_code == 422
    assert "run_id" in resp.json()["detail"]["fields"]


def test_gate_detail_and_list(gate_client: tuple[TestClient, str]) -> None:
    client, run_id = gate_client
    created = client.post(
        "/api/v1/research/gates/evaluate",
        json={"run_id": run_id, "policy_version": "1.0"},
    ).json()
    gate_run_id = created["gate_run_id"]

    detail = client.get(f"/api/v1/research/gates/{gate_run_id}")
    assert detail.status_code == 200
    assert detail.json()["gate_run_id"] == gate_run_id

    listed = client.get(f"/api/v1/research/gates?run_id={run_id}").json()["items"]
    assert any(i["gate_run_id"] == gate_run_id for i in listed)


def test_gate_detail_unknown_404(gate_client: tuple[TestClient, str]) -> None:
    client, _run_id = gate_client
    resp = client.get("/api/v1/research/gates/gate_missing")
    assert resp.status_code == 404


def test_invalidate_gate_is_append_only(gate_client: tuple[TestClient, str]) -> None:
    client, run_id = gate_client
    created = client.post(
        "/api/v1/research/gates/evaluate",
        json={"run_id": run_id, "policy_version": "1.0"},
    ).json()
    gate_run_id = created["gate_run_id"]

    resp = client.post(
        f"/api/v1/research/gates/{gate_run_id}/invalidate",
        json={"reason": "fixture correction", "actor": "test"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "invalidated"
    assert body["invalidation_reason"] == "fixture correction"
    assert body["overall_status"] == created["overall_status"]  # unchanged evaluation content

    second = client.post(
        f"/api/v1/research/gates/{gate_run_id}/invalidate",
        json={"reason": "again", "actor": "test"},
    )
    assert second.status_code == 409


def test_invalidate_gate_unknown_404(gate_client: tuple[TestClient, str]) -> None:
    client, _run_id = gate_client
    resp = client.post(
        "/api/v1/research/gates/gate_missing/invalidate",
        json={"reason": "x", "actor": "test"},
    )
    assert resp.status_code == 404


def test_gate_post_allowed_paper_post_blocked(gate_client: tuple[TestClient, str]) -> None:
    client, run_id = gate_client
    assert client.post("/api/v1/status").status_code == 405
    resp = client.post(
        "/api/v1/research/gates/evaluate",
        json={"run_id": run_id, "policy_version": "1.0"},
    )
    assert resp.status_code == 200
