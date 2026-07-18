"""Integration tests for the Validation Study API (Issue #249 / P4.7d).

Mirrors ``tests/research/test_gate_api.py`` (#248) / ``test_robustness_api.py``
(#247): same FastAPI dependency-override fixture style, public/synthetic BTC
fixture data only — no private Strategy V1 numbers, no live/paper promotion
anywhere in this surface. A Study aggregates already-produced evidence; it
runs no second backtest engine and re-evaluates no gate.
"""

from __future__ import annotations

import json
import os
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
    get_validation_service,
)
from research.gate_service import GateService
from research.robustness_service import RobustnessOrchestrationService
from research.service import ResearchReadService
from research.validation_service import ValidationStudyService
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
        "name": "validation study base experiment",
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
def validation_client(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[TestClient, dict[str, str]]:
    """A completed base experiment + a completed bootstrap robustness test +

    an evaluated gate result + a client wired to the validation API."""

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

    def _validation() -> ValidationStudyService:
        return ValidationStudyService(tmp_path, repo_root=REPO_ROOT)

    # Gate evaluation fails closed on a dirty working tree unless a deployment
    # pin is provided — tests pin an explicit evaluation SHA (Issue #248 P2).
    monkeypatch.setenv("RESEARCH_EVALUATION_GIT_SHA", "a" * 40)

    app.dependency_overrides[get_research_service] = _read
    app.dependency_overrides[get_research_write_service] = _write
    app.dependency_overrides[get_robustness_service] = _robustness
    app.dependency_overrides[get_gate_service] = _gate
    app.dependency_overrides[get_validation_service] = _validation
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

    run_id = client.get(f"/api/v1/research/experiments/{base_experiment_id}").json()[
        "summary"
    ]["run_id"]
    assert run_id

    robustness_created = client.post(
        "/api/v1/research/robustness",
        json={
            "base_experiment_id": base_experiment_id,
            "test_type": "bootstrap",
            "config": {"block_length": 2, "n_simulations": 20, "seed": 1},
        },
    ).json()
    robustness_id = robustness_created["robustness_id"]
    client.post(f"/api/v1/research/robustness/{robustness_id}/start")
    rob_deadline = time.time() + 90
    rob_status = "queued"
    while time.time() < rob_deadline:
        rob_status = client.get(
            f"/api/v1/research/robustness/{robustness_id}/status"
        ).json()["status"]
        if rob_status in {"completed", "failed"}:
            break
        time.sleep(0.2)
    assert rob_status == "completed", rob_status

    gate_resp = client.post(
        "/api/v1/research/gates/evaluate",
        json={"run_id": run_id, "policy_version": "1.0", "robustness_run_ids": [robustness_id]},
    )
    assert gate_resp.status_code == 200, gate_resp.text
    gate_created = gate_resp.json()
    gate_run_id = gate_created["gate_run_id"]

    ids = {
        "base_experiment_id": base_experiment_id,
        "run_id": run_id,
        "robustness_id": robustness_id,
        "gate_run_id": gate_run_id,
    }
    try:
        yield client, ids
    finally:
        app.dependency_overrides.pop(get_research_service, None)
        app.dependency_overrides.pop(get_research_write_service, None)
        app.dependency_overrides.pop(get_robustness_service, None)
        app.dependency_overrides.pop(get_gate_service, None)
        app.dependency_overrides.pop(get_validation_service, None)


def test_create_validation_study_aggregates_evidence(
    validation_client: tuple[TestClient, dict[str, str]],
) -> None:
    client, ids = validation_client
    resp = client.post(
        "/api/v1/research/validation",
        json={
            "name": "synthetic BTC trend study",
            "experiment_id": ids["base_experiment_id"],
            "robustness_ids": [ids["robustness_id"]],
            "gate_run_ids": [ids["gate_run_id"]],
            "notes": "fixture-driven aggregate",
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["already_exists"] is False
    study = body["study"]
    assert study["study_id"].startswith("study_")
    assert study["status"] == "open"
    assert study["decision"] is None
    assert study["experiment_id"] == ids["base_experiment_id"]
    assert study["run_id"] == ids["run_id"]
    assert study["robustness_ids"] == [ids["robustness_id"]]
    assert study["gate_run_ids"] == [ids["gate_run_id"]]

    # Aggregated from the immutable evidence snapshot — not re-computed.
    assert study["experiments"][0]["experiment_id"] == ids["base_experiment_id"]
    assert study["experiments"][0]["run_id"] == ids["run_id"]
    assert study["robustness"][0]["robustness_id"] == ids["robustness_id"]
    assert study["robustness_by_type"]["bootstrap"][0]["robustness_id"] == ids["robustness_id"]
    assert study["gates"][0]["gate_run_id"] == ids["gate_run_id"]
    assert study["gates"][0]["promotion_action"] == "none"

    snapshot = study["evidence_snapshot"]
    assert snapshot["snapshot_id"].startswith("evsnap_")
    assert snapshot["primary"]["run_id"] == ids["run_id"]
    assert len(snapshot["primary"]["checksums_digest"]) == 64
    assert study["evidence_integrity"]["ok"] is True

    progress = study["progress"]
    assert progress["experiments"] == {"total": 1, "complete": 1}
    assert progress["robustness"]["total"] == 1
    assert progress["gates"]["total"] == 1

    repro = study["reproducibility"]
    assert repro["source"] == "gate_run"
    assert repro["evidence_snapshot_id"] == snapshot["snapshot_id"]
    assert len(repro["dataset_content_hash"]) == 64
    assert repro["policy_version"] == "1.0"
    assert len(repro["policy_content_hash"]) == 64


def test_create_validation_study_is_idempotent(
    validation_client: tuple[TestClient, dict[str, str]],
) -> None:
    client, ids = validation_client
    payload = {
        "experiment_id": ids["base_experiment_id"],
        "robustness_ids": [ids["robustness_id"]],
        "gate_run_ids": [ids["gate_run_id"]],
    }
    first = client.post("/api/v1/research/validation", json=payload).json()
    second = client.post("/api/v1/research/validation", json=payload).json()
    assert first["study_id"] == second["study_id"]
    assert first["already_exists"] is False
    assert second["already_exists"] is True

    listed = client.get("/api/v1/research/validation").json()["items"]
    matching = [i for i in listed if i["study_id"] == first["study_id"]]
    assert len(matching) == 1


def test_create_validation_study_rejects_unknown_experiment(
    validation_client: tuple[TestClient, dict[str, str]],
) -> None:
    client, _ids = validation_client
    resp = client.post(
        "/api/v1/research/validation",
        json={"experiment_id": "exp_missing"},
    )
    assert resp.status_code == 422
    assert "experiment_id" in resp.json()["detail"]["fields"]


def test_create_validation_study_rejects_unknown_robustness_id(
    validation_client: tuple[TestClient, dict[str, str]],
) -> None:
    client, ids = validation_client
    resp = client.post(
        "/api/v1/research/validation",
        json={
            "experiment_id": ids["base_experiment_id"],
            "robustness_ids": ["rob_missing"],
        },
    )
    assert resp.status_code == 422
    assert "robustness_ids" in resp.json()["detail"]["fields"]


def test_create_validation_study_rejects_unknown_gate_run_id(
    validation_client: tuple[TestClient, dict[str, str]],
) -> None:
    client, ids = validation_client
    resp = client.post(
        "/api/v1/research/validation",
        json={
            "experiment_id": ids["base_experiment_id"],
            "gate_run_ids": ["gate_missing"],
        },
    )
    assert resp.status_code == 422
    assert "gate_run_ids" in resp.json()["detail"]["fields"]


def _complete_second_experiment(client: TestClient, tmp_path: Path) -> tuple[str, str]:
    """Create and finish a second experiment (run B) under the same catalog."""
    _catalog_path, payload = _catalog_and_lab_payload(tmp_path)
    payload = {**payload, "name": "validation study other experiment", "random_seed": 11}
    created = client.post("/api/v1/research/experiments", json=payload).json()
    experiment_id = created["experiment_id"]
    started = client.post(f"/api/v1/research/experiments/{experiment_id}/start")
    assert started.status_code == 200, started.text
    deadline = time.time() + 60
    status = "queued"
    while time.time() < deadline:
        status = client.get(f"/api/v1/research/experiments/{experiment_id}/status").json()[
            "status"
        ]
        if status in {"completed", "failed"}:
            break
        time.sleep(0.2)
    assert status == "completed", status
    run_id = client.get(f"/api/v1/research/experiments/{experiment_id}").json()["summary"][
        "run_id"
    ]
    assert run_id
    return experiment_id, run_id


def test_create_validation_study_rejects_cross_run_robustness(
    validation_client: tuple[TestClient, dict[str, str]],
    tmp_path: Path,
) -> None:
    """Study for run B cannot pin robustness whose base_run_id is run A."""
    client, ids = validation_client
    other_experiment_id, _other_run_id = _complete_second_experiment(client, tmp_path)
    resp = client.post(
        "/api/v1/research/validation",
        json={
            "experiment_id": other_experiment_id,
            "robustness_ids": [ids["robustness_id"]],
        },
    )
    assert resp.status_code == 422, resp.text
    fields = resp.json()["detail"]["fields"]
    assert "robustness_ids" in fields
    assert "not in study pinned runs" in fields["robustness_ids"]


def test_create_validation_study_rejects_cross_run_gate(
    validation_client: tuple[TestClient, dict[str, str]],
    tmp_path: Path,
) -> None:
    """Study for run B cannot pin a gate whose run_id is run A."""
    client, ids = validation_client
    other_experiment_id, _other_run_id = _complete_second_experiment(client, tmp_path)
    resp = client.post(
        "/api/v1/research/validation",
        json={
            "experiment_id": other_experiment_id,
            "gate_run_ids": [ids["gate_run_id"]],
        },
    )
    assert resp.status_code == 422, resp.text
    fields = resp.json()["detail"]["fields"]
    assert "gate_run_ids" in fields
    assert "not in study pinned runs" in fields["gate_run_ids"]


def test_create_validation_study_rejects_missing_experiment_id(
    validation_client: tuple[TestClient, dict[str, str]],
) -> None:
    client, _ids = validation_client
    resp = client.post("/api/v1/research/validation", json={})
    assert resp.status_code == 422
    assert "experiment_id" in resp.json()["detail"]["fields"]


def test_validation_study_detail_and_list_filters(
    validation_client: tuple[TestClient, dict[str, str]],
) -> None:
    client, ids = validation_client
    created = client.post(
        "/api/v1/research/validation",
        json={"experiment_id": ids["base_experiment_id"]},
    ).json()
    study_id = created["study_id"]

    detail = client.get(f"/api/v1/research/validation/{study_id}")
    assert detail.status_code == 200
    assert detail.json()["study_id"] == study_id

    by_experiment = client.get(
        f"/api/v1/research/validation?experiment_id={ids['base_experiment_id']}"
    ).json()["items"]
    assert any(i["study_id"] == study_id for i in by_experiment)

    by_status = client.get("/api/v1/research/validation?status=open").json()["items"]
    assert any(i["study_id"] == study_id for i in by_status)


def test_validation_study_detail_unknown_404(
    validation_client: tuple[TestClient, dict[str, str]],
) -> None:
    client, _ids = validation_client
    resp = client.get("/api/v1/research/validation/study_missing")
    assert resp.status_code == 404


def test_decide_validation_study_records_human_owned_decision(
    validation_client: tuple[TestClient, dict[str, str]],
) -> None:
    client, ids = validation_client
    created = client.post(
        "/api/v1/research/validation",
        json={
            "experiment_id": ids["base_experiment_id"],
            "gate_run_ids": [ids["gate_run_id"]],
        },
    ).json()
    study_id = created["study_id"]

    resp = client.post(
        f"/api/v1/research/validation/{study_id}/decision",
        json={
            "outcome": "accept",
            "rationale": "synthetic gates passed under fixture policy",
            "decided_by": "reviewer",
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "decided"
    assert body["decision"]["outcome"] == "accept"
    assert body["decision"]["decided_by"] == "reviewer"
    assert (
        body["decision"]["evidence_snapshot_id"]
        == body["evidence_snapshot"]["snapshot_id"]
    )

    # No promotion trigger anywhere in the response (#249 non-scope: live/paper promotion).
    assert "promotion_action" not in body["decision"]

    second = client.post(
        f"/api/v1/research/validation/{study_id}/decision",
        json={"outcome": "reject", "rationale": "changed my mind"},
    )
    assert second.status_code == 409


def test_decide_validation_study_rejects_missing_rationale(
    validation_client: tuple[TestClient, dict[str, str]],
) -> None:
    client, ids = validation_client
    created = client.post(
        "/api/v1/research/validation",
        json={"experiment_id": ids["base_experiment_id"]},
    ).json()
    study_id = created["study_id"]

    resp = client.post(
        f"/api/v1/research/validation/{study_id}/decision",
        json={"outcome": "accept"},
    )
    assert resp.status_code == 409
    assert "rationale" in resp.json()["detail"]["fields"]


def test_decide_validation_study_rejects_invalid_outcome(
    validation_client: tuple[TestClient, dict[str, str]],
) -> None:
    client, ids = validation_client
    created = client.post(
        "/api/v1/research/validation",
        json={"experiment_id": ids["base_experiment_id"]},
    ).json()
    study_id = created["study_id"]

    resp = client.post(
        f"/api/v1/research/validation/{study_id}/decision",
        json={"outcome": "promote_live", "rationale": "n/a"},
    )
    assert resp.status_code == 409
    assert "outcome" in resp.json()["detail"]["fields"]


def test_decide_validation_study_unknown_404(
    validation_client: tuple[TestClient, dict[str, str]],
) -> None:
    client, _ids = validation_client
    resp = client.post(
        "/api/v1/research/validation/study_missing/decision",
        json={"outcome": "accept", "rationale": "n/a"},
    )
    assert resp.status_code == 404


def test_validation_post_allowed_paper_post_blocked(
    validation_client: tuple[TestClient, dict[str, str]],
) -> None:
    client, ids = validation_client
    assert client.post("/api/v1/status").status_code == 405
    resp = client.post(
        "/api/v1/research/validation",
        json={"experiment_id": ids["base_experiment_id"]},
    )
    assert resp.status_code == 200


def test_create_pins_run_a_despite_later_complete_run_b(
    validation_client: tuple[TestClient, dict[str, str]],
) -> None:
    """Create pins run A; a later complete run B for the same experiment must

    not change the study's returned evidence (P1 immutable binding)."""
    client, ids = validation_client
    created = client.post(
        "/api/v1/research/validation",
        json={
            "experiment_id": ids["base_experiment_id"],
            "robustness_ids": [ids["robustness_id"]],
            "gate_run_ids": [ids["gate_run_id"]],
        },
    ).json()
    study_id = created["study_id"]
    pinned_run = created["study"]["run_id"]
    assert pinned_run == ids["run_id"]

    # Simulate a newer complete registry entry for the same experiment
    # (different run_id). Live experiment_detail would prefer this row;
    # the study must keep resolving the pinned run A.
    from research.registry import ExperimentRegistry

    root = Path(os.environ["RESEARCH_ARTIFACTS_ROOT"])
    registry = ExperimentRegistry(root)
    original = registry.show(pinned_run, verify=False)
    registry._append(  # noqa: SLF001 — intentional drift fixture
        {
            "experiment_id": original.experiment_id,
            "run_id": "run_later_complete_b",
            "attempt_id": "attempt_later_b",
            "status": "complete",
            "strategy_version": original.strategy_version,
            "dataset_version": original.dataset_version,
            "cost_model_version": original.cost_model_version,
            "benchmark_ref": original.benchmark_ref,
            "created_at": "2099-01-01T00:00:00.000000Z",
            "artifact_path": original.artifact_path,
            "checksums": original.checksums,
        }
    )

    detail = client.get(f"/api/v1/research/validation/{study_id}")
    assert detail.status_code == 200, detail.text
    body = detail.json()
    assert body["run_id"] == pinned_run
    assert body["experiments"][0]["run_id"] == pinned_run
    assert body["evidence_snapshot"]["primary"]["run_id"] == pinned_run
    assert body["evidence_integrity"]["ok"] is True

    # Contrast: live experiment read resolves to the newest registry row.
    live = client.get(
        f"/api/v1/research/experiments/{ids['base_experiment_id']}"
    ).json()
    assert live["summary"]["run_id"] == "run_later_complete_b"


def test_create_rejects_failed_or_invalidated_run(
    validation_client: tuple[TestClient, dict[str, str]],
) -> None:
    client, ids = validation_client
    from research.registry import ExperimentRegistry

    root = Path(os.environ["RESEARCH_ARTIFACTS_ROOT"])
    registry = ExperimentRegistry(root)
    registry.invalidate(ids["run_id"], reason="fixture invalidate", actor="test")

    resp = client.post(
        "/api/v1/research/validation",
        json={"experiment_id": ids["base_experiment_id"]},
    )
    assert resp.status_code == 422, resp.text
    assert "experiment_id" in resp.json()["detail"]["fields"]


def test_decision_bound_to_snapshot_survives_post_decision_latest_drift(
    validation_client: tuple[TestClient, dict[str, str]],
) -> None:
    client, ids = validation_client
    created = client.post(
        "/api/v1/research/validation",
        json={
            "experiment_id": ids["base_experiment_id"],
            "gate_run_ids": [ids["gate_run_id"]],
        },
    ).json()
    study_id = created["study_id"]
    snapshot_id = created["study"]["evidence_snapshot"]["snapshot_id"]
    pinned_run = created["study"]["run_id"]

    decided = client.post(
        f"/api/v1/research/validation/{study_id}/decision",
        json={
            "outcome": "accept",
            "rationale": "bound to immutable snapshot",
            "decided_by": "reviewer",
        },
    )
    assert decided.status_code == 200, decided.text
    assert decided.json()["decision"]["evidence_snapshot_id"] == snapshot_id

    from research.registry import ExperimentRegistry

    root = Path(os.environ["RESEARCH_ARTIFACTS_ROOT"])
    registry = ExperimentRegistry(root)
    original = registry.show(pinned_run, verify=False)
    registry._append(  # noqa: SLF001 — intentional drift fixture
        {
            "experiment_id": original.experiment_id,
            "run_id": "run_post_decision_drift",
            "attempt_id": "attempt_post_decision",
            "status": "complete",
            "strategy_version": original.strategy_version,
            "dataset_version": original.dataset_version,
            "cost_model_version": original.cost_model_version,
            "benchmark_ref": original.benchmark_ref,
            "created_at": "2099-06-01T00:00:00.000000Z",
            "artifact_path": original.artifact_path,
            "checksums": original.checksums,
        }
    )

    detail = client.get(f"/api/v1/research/validation/{study_id}")
    assert detail.status_code == 200, detail.text
    body = detail.json()
    assert body["run_id"] == pinned_run
    assert body["decision"]["evidence_snapshot_id"] == snapshot_id
    assert body["evidence_snapshot"]["primary"]["run_id"] == pinned_run
    assert body["evidence_integrity"]["ok"] is True


def test_decided_study_fail_closed_when_pinned_run_invalidated(
    validation_client: tuple[TestClient, dict[str, str]],
) -> None:
    client, ids = validation_client
    created = client.post(
        "/api/v1/research/validation",
        json={"experiment_id": ids["base_experiment_id"]},
    ).json()
    study_id = created["study_id"]

    decided = client.post(
        f"/api/v1/research/validation/{study_id}/decision",
        json={
            "outcome": "reject",
            "rationale": "will invalidate underlying evidence next",
            "decided_by": "reviewer",
        },
    )
    assert decided.status_code == 200, decided.text

    from research.registry import ExperimentRegistry

    root = Path(os.environ["RESEARCH_ARTIFACTS_ROOT"])
    ExperimentRegistry(root).invalidate(
        ids["run_id"], reason="post-decision invalidate", actor="test"
    )

    detail = client.get(f"/api/v1/research/validation/{study_id}")
    assert detail.status_code == 409, detail.text
    assert "fields" in detail.json()["detail"]
