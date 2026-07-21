"""Backend authentication regression tests for Research mutations (Issue #376)."""

from __future__ import annotations

from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from paper_trading.readonly_api import app
from research.api import get_gate_service, get_research_write_service


class _RecordingWriteService:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def create_experiment(self, _payload: dict[str, object]) -> dict[str, str]:
        self.calls.append("create")
        return {"experiment_id": "exp_auth", "status": "created"}

    def start_experiment(self, experiment_id: str) -> dict[str, str]:
        self.calls.append("start")
        return {"experiment_id": experiment_id, "status": "queued"}


class _RecordingGateService:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def evaluate(self, _payload: dict[str, object]) -> dict[str, str]:
        self.calls.append("evaluate")
        return {"gate_run_id": "gate_auth", "status": "evaluated"}

    def invalidate(
        self, gate_run_id: str, _payload: dict[str, object]
    ) -> dict[str, str]:
        self.calls.append("invalidate")
        return {"gate_run_id": gate_run_id, "status": "invalidated"}


@pytest.fixture
def auth_client(
    monkeypatch: pytest.MonkeyPatch,
) -> Generator[
    tuple[TestClient, _RecordingWriteService, _RecordingGateService], None, None
]:
    monkeypatch.setenv("RESEARCH_WRITE_API_KEY", "research-test-key")
    write_service = _RecordingWriteService()
    gate_service = _RecordingGateService()
    app.dependency_overrides[get_research_write_service] = lambda: write_service
    app.dependency_overrides[get_gate_service] = lambda: gate_service
    try:
        yield TestClient(app), write_service, gate_service
    finally:
        app.dependency_overrides.pop(get_research_write_service, None)
        app.dependency_overrides.pop(get_gate_service, None)


def test_unauthenticated_research_posts_fail_before_mutation(
    auth_client: tuple[TestClient, _RecordingWriteService, _RecordingGateService],
) -> None:
    client, write_service, gate_service = auth_client

    responses = [
        client.post("/api/v1/research/experiments", json={}),
        client.post("/api/v1/research/experiments/exp_auth/start"),
        client.post("/api/v1/research/robustness", json={}),
        client.post("/api/v1/research/robustness/robustness_auth/start"),
        client.post("/api/v1/research/gates/evaluate", json={}),
        client.post("/api/v1/research/gates/gate_auth/invalidate", json={}),
        client.post("/api/v1/research/scorecards/evaluate", json={}),
        client.post(
            "/api/v1/research/scorecards/scorecard_auth/invalidate", json={}
        ),
        client.post("/api/v1/research/validation", json={}),
        client.post(
            "/api/v1/research/validation/study_auth/decision", json={}
        ),
    ]

    assert [response.status_code for response in responses] == [403] * 10
    assert write_service.calls == []
    assert gate_service.calls == []


def test_authenticated_research_posts_reach_mutation_services(
    auth_client: tuple[TestClient, _RecordingWriteService, _RecordingGateService],
) -> None:
    client, write_service, gate_service = auth_client
    headers = {"X-API-Key": "research-test-key"}

    responses = [
        client.post("/api/v1/research/experiments", json={}, headers=headers),
        client.post(
            "/api/v1/research/experiments/exp_auth/start", headers=headers
        ),
        client.post("/api/v1/research/gates/evaluate", json={}, headers=headers),
        client.post(
            "/api/v1/research/gates/gate_auth/invalidate",
            json={},
            headers=headers,
        ),
    ]

    assert [response.status_code for response in responses] == [200, 200, 200, 200]
    assert write_service.calls == ["create", "start"]
    assert gate_service.calls == ["evaluate", "invalidate"]
