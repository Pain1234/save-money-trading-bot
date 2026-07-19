"""Integration tests for the scorecard API (#291)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
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
        "name": "scorecard base experiment",
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
def scorecard_client(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[TestClient, str]:
    catalog_path, payload = _catalog_and_lab_payload(tmp_path)
    monkeypatch.setenv("RESEARCH_ARTIFACTS_ROOT", str(tmp_path))
    monkeypatch.setenv("RESEARCH_DATASET_CATALOG_PATH", str(catalog_path))
    monkeypatch.setenv("RESEARCH_REPO_ROOT", str(REPO_ROOT))
    monkeypatch.setenv("RESEARCH_ALLOW_DIRTY_GIT", "1")
    monkeypatch.setenv("RESEARCH_EVALUATION_GIT_SHA", "b" * 40)
    eval_image_root = tmp_path / ".evaluation_image_root"
    eval_image_root.mkdir()

    def _read() -> ResearchReadService:
        return ResearchReadService(tmp_path)

    def _write() -> ResearchWriteService:
        return ResearchWriteService(tmp_path, repo_root=REPO_ROOT, allow_dirty_git=True)

    def _robustness() -> RobustnessOrchestrationService:
        return RobustnessOrchestrationService(
            tmp_path, repo_root=REPO_ROOT, allow_dirty_git=True
        )

    def _gate() -> GateService:
        return GateService(tmp_path, repo_root=eval_image_root)

    def _scorecard() -> ScorecardService:
        return ScorecardService(tmp_path, repo_root=eval_image_root)

    app.dependency_overrides[get_research_service] = _read
    app.dependency_overrides[get_research_write_service] = _write
    app.dependency_overrides[get_robustness_service] = _robustness
    app.dependency_overrides[get_gate_service] = _gate
    app.dependency_overrides[get_scorecard_service] = _scorecard
    client = TestClient(app)

    created = client.post("/api/v1/research/experiments", json=payload).json()
    base_experiment_id = created["experiment_id"]
    started = client.post(f"/api/v1/research/experiments/{base_experiment_id}/start")
    assert started.status_code == 200, started.text

    import time

    deadline = time.time() + 60
    status = "queued"
    while time.time() < deadline:
        status_body = client.get(
            f"/api/v1/research/experiments/{base_experiment_id}/status"
        ).json()
        status = status_body["status"]
        if status in {"completed", "failed"}:
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
        app.dependency_overrides.pop(get_scorecard_service, None)


def test_list_scorecard_policies(scorecard_client: tuple[TestClient, str]) -> None:
    client, _run_id = scorecard_client
    resp = client.get("/api/v1/research/scorecard-policies")
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert any(i["version"] == "1.0" and len(i["content_hash"]) == 64 for i in items)


def test_evaluate_scorecard_idempotent(scorecard_client: tuple[TestClient, str]) -> None:
    client, run_id = scorecard_client
    payload = {"run_id": run_id, "policy_version": "1.0"}
    first = client.post("/api/v1/research/scorecards/evaluate", json=payload)
    assert first.status_code == 200, first.text
    body = first.json()
    assert body["scorecard_id"].startswith("sc_")
    assert body["evidence_integrity"]["ok"] is True
    assert body["global_profile"]["parameter_area"]["status"] == "NOT_AVAILABLE"
    assert body["promotion_action"] == "none"
    second = client.post("/api/v1/research/scorecards/evaluate", json=payload)
    assert second.status_code == 200
    assert second.json()["scorecard_id"] == body["scorecard_id"]
    listed = client.get(f"/api/v1/research/scorecards?run_id={run_id}")
    assert listed.status_code == 200
    assert listed.json()["count"] == 1
    detail = client.get(f"/api/v1/research/scorecards/{body['scorecard_id']}")
    assert detail.status_code == 200
    assert detail.json()["scorecard_id"] == body["scorecard_id"]


def test_invalidate_scorecard(scorecard_client: tuple[TestClient, str]) -> None:
    client, run_id = scorecard_client
    created = client.post(
        "/api/v1/research/scorecards/evaluate",
        json={"run_id": run_id, "policy_version": "1.0"},
    ).json()
    resp = client.post(
        f"/api/v1/research/scorecards/{created['scorecard_id']}/invalidate",
        json={"reason": "fixture correction", "actor": "test"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "invalidated"
