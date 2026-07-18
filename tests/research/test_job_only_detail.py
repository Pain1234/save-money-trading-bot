"""Regression: failed job-only experiments must return Lab-safe detail (#274 follow-up)."""

from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient
from paper_trading.readonly_api import app
from research.api import get_research_service, get_research_write_service
from research.jobs import ResearchJob, ResearchJobStore
from research.service import ResearchReadService
from research.write_service import ResearchWriteService

from tests.research.fixtures import align_spec_to_bundle, btc_bundle

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_failed_job_detail_has_full_config_shape(tmp_path: Path) -> None:
    """Job-only failed runs must not return config={} (breaks Lab detail page)."""
    bundle = btc_bundle()
    spec = align_spec_to_bundle(tmp_path, bundle, symbols=["BTC"])
    artifacts = tmp_path / "artifacts"
    artifacts.mkdir()
    store = ResearchJobStore(artifacts)
    exp_id = "exp_failed_job_only_001"
    pending = store.pending_spec_path(exp_id)
    pending.parent.mkdir(parents=True, exist_ok=True)
    pending.write_text(
        json.dumps(
            {
                **json.loads(
                    # minimal dump via model
                    spec.model_dump_json()
                ),
            }
        ),
        encoding="utf-8",
    )
    job = ResearchJob(
        experiment_id=exp_id,
        status="failed",
        name="failed lab",
        dataset_catalog_id="fixture",
        created_at="2024-01-01T00:00:00+00:00",
        updated_at="2024-01-01T00:00:01+00:00",
        started_at="2024-01-01T00:00:00+00:00",
        finished_at="2024-01-01T00:00:01+00:00",
        error="time_range.start is before DatasetManifest.start_timestamp",
        error_detail="time_range.start is before DatasetManifest.start_timestamp",
        run_id="run_x",
        attempt_id="att_x",
    )
    store.save(job)

    def _read() -> ResearchReadService:
        return ResearchReadService(artifacts)

    def _write() -> ResearchWriteService:
        return ResearchWriteService(artifacts, repo_root=REPO_ROOT, allow_dirty_git=True)

    app.dependency_overrides[get_research_service] = _read
    app.dependency_overrides[get_research_write_service] = _write
    client = TestClient(app)
    try:
        resp = client.get(f"/api/v1/research/experiments/{exp_id}")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["config"]["symbols"] == ["BTC"]
        assert isinstance(body["config"]["symbols"], list)
        assert body["config"]["timeframe"] == "Nicht verfügbar"
        assert body["job"]["status"] == "failed"
        assert "time_range.start" in (body["job"]["error"] or "")
        assert body["integrity"]["ok"] is False
    finally:
        app.dependency_overrides.clear()
