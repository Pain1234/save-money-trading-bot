"""Tests for research write API / Strategy Lab jobs (Issue #242)."""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from paper_trading.readonly_api import app
from research.api import get_research_service, get_research_write_service
from research.service import ResearchReadService
from research.write_service import ResearchWriteService

from tests.research.fixtures import align_spec_to_bundle, btc_bundle

REPO_ROOT = Path(__file__).resolve().parents[2]


def _catalog_and_bundle(tmp_path: Path) -> tuple[Path, dict[str, object], dict[str, object]]:
    bundle = btc_bundle()
    spec = align_spec_to_bundle(tmp_path, bundle, symbols=["BTC"])
    bundle_path = tmp_path / "bundle.json"
    bundle_path.write_text(
        bundle.model_dump_json(),
        encoding="utf-8",
    )
    # Manifest path may be absolute under tmp_path — keep as written in spec.
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
    defaults = {
        "strategy_id": "trend_v1",
        "strategy_version": spec.strategy_version,
        "name": "UI lab smoke experiment",
        "notes": "from test",
        "symbols": ["BTC"],
        "timeframe": "1D",
        "time_range": {
            "start": spec.time_range.start.strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
            "end": spec.time_range.end.strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
        },
        "starting_capital": str(spec.starting_capital),
        "parameters": {
            k: v
            for k, v in spec.parameters.items()
            if k != "strategy_id"
        },
        "fee_assumption": {
            "entry_fee_rate": str(spec.fee_assumption.entry_fee_rate),
            "exit_fee_rate": str(spec.fee_assumption.exit_fee_rate),
        },
        "slippage_assumption": {
            "slippage_bps": str(spec.slippage_assumption.slippage_bps),
        },
        "random_seed": 7,
        "dataset_catalog_id": "fixture-btc",
        "owner": "test",
    }
    return catalog_path, defaults, {
        "bundle_path": str(bundle_path),
        "spec": spec,
    }


@pytest.fixture
def write_client(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[TestClient, dict[str, object]]:
    catalog_path, payload, meta = _catalog_and_bundle(tmp_path)
    monkeypatch.setenv("RESEARCH_ARTIFACTS_ROOT", str(tmp_path))
    monkeypatch.setenv("RESEARCH_DATASET_CATALOG_PATH", str(catalog_path))
    monkeypatch.setenv("RESEARCH_REPO_ROOT", str(REPO_ROOT))
    monkeypatch.setenv("RESEARCH_ALLOW_DIRTY_GIT", "1")

    def _read() -> ResearchReadService:
        return ResearchReadService(tmp_path)

    def _write() -> ResearchWriteService:
        return ResearchWriteService(
            tmp_path, repo_root=REPO_ROOT, allow_dirty_git=True
        )

    app.dependency_overrides[get_research_service] = _read
    app.dependency_overrides[get_research_write_service] = _write
    client = TestClient(app)
    yield client, payload
    app.dependency_overrides.pop(get_research_service, None)
    app.dependency_overrides.pop(get_research_write_service, None)


def test_list_strategies(write_client: tuple[TestClient, dict[str, object]]) -> None:
    client, _ = write_client
    body = client.get("/api/v1/research/strategies").json()
    ids = {i["strategy_id"] for i in body["items"]}
    assert "trend_v1" in ids


def test_strategy_schema(write_client: tuple[TestClient, dict[str, object]]) -> None:
    client, _ = write_client
    body = client.get("/api/v1/research/strategies/trend_v1/schema").json()
    assert body["strategy_version"]
    assert "parameters_schema" in body
    assert "parameter_defaults" in body
    assert client.get("/api/v1/research/strategies/unknown/schema").status_code == 404


def test_create_valid_and_invalid(
    write_client: tuple[TestClient, dict[str, object]],
) -> None:
    client, payload = write_client
    ok = client.post("/api/v1/research/experiments", json=payload)
    assert ok.status_code == 200
    experiment_id = ok.json()["experiment_id"]
    assert experiment_id.startswith("exp_")

    bad = dict(payload)
    bad["strategy_id"] = "nope"
    resp = client.post("/api/v1/research/experiments", json=bad)
    assert resp.status_code == 422
    assert "strategy_id" in resp.json()["detail"]["fields"]

    bad2 = dict(payload)
    bad2["starting_capital"] = "-1"
    assert client.post("/api/v1/research/experiments", json=bad2).status_code == 422


def test_start_status_complete_and_double_start(
    write_client: tuple[TestClient, dict[str, object]],
) -> None:
    client, payload = write_client
    created = client.post("/api/v1/research/experiments", json=payload).json()
    experiment_id = created["experiment_id"]

    started = client.post(f"/api/v1/research/experiments/{experiment_id}/start")
    assert started.status_code == 200
    assert started.json()["status"] in {"queued", "running", "completed"}

    # Double start while active or after should be rejected once completed/running.
    deadline = time.time() + 60
    final_status = None
    while time.time() < deadline:
        status = client.get(
            f"/api/v1/research/experiments/{experiment_id}/status"
        ).json()
        final_status = status["status"]
        if final_status in {"completed", "failed"}:
            break
        time.sleep(0.2)

    assert final_status in {"completed", "failed"}
    if final_status == "completed":
        detail = client.get(f"/api/v1/research/experiments/{experiment_id}").json()
        assert detail["integrity"]["ok"] is True
        listed = client.get("/api/v1/research/experiments").json()["items"]
        assert any(i["experiment_id"] == experiment_id for i in listed)

    again = client.post(f"/api/v1/research/experiments/{experiment_id}/start")
    assert again.status_code == 409


def test_unknown_status_404(
    write_client: tuple[TestClient, dict[str, object]],
) -> None:
    client, _ = write_client
    assert (
        client.get("/api/v1/research/experiments/exp_missing/status").status_code
        == 404
    )


def test_research_post_allowed_paper_post_blocked(
    write_client: tuple[TestClient, dict[str, object]],
) -> None:
    client, payload = write_client
    assert client.post("/api/v1/status").status_code == 405
    assert client.post("/api/v1/research/experiments", json=payload).status_code == 200


def test_parallel_start_is_atomic(
    write_client: tuple[TestClient, dict[str, object]],
) -> None:
    from concurrent.futures import ThreadPoolExecutor

    client, payload = write_client
    experiment_id = client.post(
        "/api/v1/research/experiments", json=payload
    ).json()["experiment_id"]

    def _start() -> int:
        return client.post(
            f"/api/v1/research/experiments/{experiment_id}/start"
        ).status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        codes = list(pool.map(lambda _: _start(), range(2)))

    assert sorted(codes) == [200, 409]

    # Wait for the single winner to finish so the process stays clean.
    deadline = time.time() + 60
    while time.time() < deadline:
        status = client.get(
            f"/api/v1/research/experiments/{experiment_id}/status"
        ).json()["status"]
        if status in {"completed", "failed"}:
            break
        time.sleep(0.2)


def test_create_terminal_is_idempotent_no_rerun(
    write_client: tuple[TestClient, dict[str, object]],
) -> None:
    client, payload = write_client
    first = client.post("/api/v1/research/experiments", json=payload).json()
    experiment_id = first["experiment_id"]
    assert first.get("already_exists") is False

    client.post(f"/api/v1/research/experiments/{experiment_id}/start")
    deadline = time.time() + 60
    while time.time() < deadline:
        status = client.get(
            f"/api/v1/research/experiments/{experiment_id}/status"
        ).json()["status"]
        if status in {"completed", "failed"}:
            break
        time.sleep(0.2)

    second = client.post("/api/v1/research/experiments", json=payload)
    assert second.status_code == 200
    body = second.json()
    assert body["experiment_id"] == experiment_id
    assert body.get("already_exists") is True
    assert body["status"] in {"completed", "failed"}
    # Must not reset to created (would enable implicit Re-run).
    assert body["status"] != "created"


def test_stale_queued_fail_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from datetime import UTC, datetime, timedelta

    from research.jobs import ResearchJob, ResearchJobStore

    monkeypatch.setenv("RESEARCH_JOB_QUEUED_STALE_SECONDS", "1")
    store = ResearchJobStore(tmp_path)
    old = (datetime.now(UTC) - timedelta(seconds=30)).strftime(
        "%Y-%m-%dT%H:%M:%S.%fZ"
    )
    job = ResearchJob(
        experiment_id="exp_stale_queued",
        status="queued",
        created_at=old,
        updated_at=old,
    )
    store.save(job)
    time.sleep(1.1)
    marked = store.mark_stale_if_needed(store.get("exp_stale_queued"))  # type: ignore[arg-type]
    assert marked is not None
    assert marked.status == "failed"
    assert marked.error is not None
    assert "queued" in marked.error.lower()


def test_job_save_is_atomic_readable(
    tmp_path: Path,
) -> None:
    from research.jobs import ResearchJob, ResearchJobStore

    store = ResearchJobStore(tmp_path)
    job = ResearchJob(
        experiment_id="exp_atomic",
        status="created",
        created_at="2024-01-01T00:00:00.000000Z",
        updated_at="2024-01-01T00:00:00.000000Z",
    )
    store.save(job)
    path = tmp_path / "artifacts" / "research" / "jobs" / "exp_atomic.json"
    assert path.is_file()
    raw = json.loads(path.read_text(encoding="utf-8"))
    assert raw["status"] == "created"
    assert not list(path.parent.glob(".*.tmp"))
