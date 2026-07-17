"""Tests for research read API (Issue #240)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from paper_trading.readonly_api import app
from research.api import get_research_service
from research.artifacts import compute_artifact_checksums
from research.service import ResearchReadService


def _write_run(
    root: Path,
    *,
    experiment_id: str,
    run_id: str,
    status: str = "complete",
    strategy_version: str = "trend-v1.0.0",
    with_metrics: bool = True,
    with_equity: bool = True,
    corrupt_metrics: bool = False,
    artifact_path_override: str | None = None,
    checksums_override: dict[str, str] | None = None,
    equity_payload: list[dict[str, object]] | None = None,
) -> Path:
    run_dir = root / "artifacts" / "research" / experiment_id / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "experiment.json").write_text(
        json.dumps(
            {
                "symbols": ["BTC", "ETH"],
                "time_range": {
                    "start": "2024-01-01T00:00:00Z",
                    "end": "2024-03-01T00:00:00Z",
                },
                "starting_capital": "100000",
                "parameters": {"strategy_id": "trend_v1", "lookback": 20},
                "fee_assumption": {"maker_bps": "1"},
                "slippage_assumption": {"bps": "2"},
                "funding_assumption": {"rate": "0"},
                "hypothesis": "smoke",
                "random_seed": 7,
                "benchmark": "buy_hold_btc",
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    (run_dir / "run_manifest.json").write_text(
        json.dumps(
            {
                "experiment_id": experiment_id,
                "run_id": run_id,
                "git_commit": "abc123def",
                "created_at_utc": "2024-06-01T12:00:00Z",
                "status": status,
                "strategy_version": strategy_version,
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    (run_dir / "costs.json").write_text(
        json.dumps({"cost_model_version": "1.0"}, sort_keys=True),
        encoding="utf-8",
    )
    if with_metrics:
        if corrupt_metrics:
            (run_dir / "metrics.json").write_text("{not-json", encoding="utf-8")
        else:
            (run_dir / "metrics.json").write_text(
                json.dumps(
                    {
                        "start_capital": "100000",
                        "end_capital": "110000",
                        "net_pnl": "10000",
                        "gross_pnl": "10500",
                        "fees": "400",
                        "slippage_costs": "100",
                        "funding_costs": "0",
                        "max_drawdown": "0.12",
                        "hit_rate": "0.55",
                        "profit_factor": "1.4",
                        "closed_trades": 10,
                        "expectancy": "100",
                        "avg_win": "200",
                        "avg_loss": "-100",
                        "benchmark_result": "0.05",
                        "status": "ok",
                    },
                    sort_keys=True,
                ),
                encoding="utf-8",
            )
    if with_equity:
        payload = equity_payload or [
            {"time": "2024-01-01T00:00:00Z", "equity": "100000"},
            {"time": "2024-02-01T00:00:00Z", "equity": "105000"},
            {"time": "2024-03-01T00:00:00Z", "equity": "110000"},
        ]
        (run_dir / "equity.json").write_text(
            json.dumps(payload),
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
        "attempt_id": "attempt-1",
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


@pytest.fixture
def research_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    _write_run(tmp_path, experiment_id="exp-alpha", run_id="run-a")
    _write_run(
        tmp_path,
        experiment_id="exp-beta",
        run_id="run-b",
        status="failed",
        strategy_version="trend-v1.0.1",
        with_metrics=False,
        with_equity=False,
    )
    client = _client_for(tmp_path, monkeypatch)
    yield client
    app.dependency_overrides.pop(get_research_service, None)


def test_overview_from_registry(research_client: TestClient) -> None:
    response = research_client.get("/api/v1/research/overview")
    assert response.status_code == 200
    body = response.json()
    assert body["experiment_count"] == 2
    assert body["completed_count"] == 1
    assert body["failed_count"] == 1
    assert body["running_available"] is True
    assert body["running_count"] == 0
    assert body["status_distribution"]["complete"] == 1
    assert body["unavailable"]["promotions"] == "Nicht verfügbar"
    assert len(body["recent_experiments"]) == 2
    alpha = next(
        e for e in body["recent_experiments"] if e["experiment_id"] == "exp-alpha"
    )
    assert alpha["integrity_ok"] is True


def test_experiments_list_and_filters(research_client: TestClient) -> None:
    all_resp = research_client.get("/api/v1/research/experiments")
    assert all_resp.status_code == 200
    assert all_resp.json()["count"] == 2

    by_status = research_client.get(
        "/api/v1/research/experiments", params={"status": "failed"}
    )
    assert by_status.json()["count"] == 1
    assert by_status.json()["items"][0]["experiment_id"] == "exp-beta"

    by_strategy = research_client.get(
        "/api/v1/research/experiments",
        params={"strategy_version": "trend-v1.0.0"},
    )
    assert by_strategy.json()["count"] == 1

    by_q = research_client.get(
        "/api/v1/research/experiments", params={"q": "alpha"}
    )
    assert by_q.json()["count"] == 1
    assert by_q.json()["items"][0]["experiment_id"] == "exp-alpha"


def test_experiment_detail_success(research_client: TestClient) -> None:
    response = research_client.get("/api/v1/research/experiments/exp-alpha")
    assert response.status_code == 200
    body = response.json()
    assert body["metadata"]["experiment_id"] == "exp-alpha"
    assert body["metadata"]["git_commit"] == "abc123def"
    assert body["metadata"]["started_at"] is None
    assert body["metadata"]["finalized_at"] == "2024-06-01T12:00:00Z"
    assert "completed_at" not in body["metadata"]
    assert body["metrics"]["net_pnl"] == "10000"
    assert body["metrics"]["sharpe"] == "Nicht verfügbar"
    assert body["metrics"]["total_return"] == "0.1"
    assert len(body["equity"]) == 3
    assert len(body["drawdown"]) == 3
    assert body["artifacts"]["has_metrics"] is True
    assert body["integrity"]["ok"] is True


def test_unknown_experiment_404(research_client: TestClient) -> None:
    response = research_client.get("/api/v1/research/experiments/missing-exp")
    assert response.status_code == 404


def test_missing_artifacts_controlled(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_run(
        tmp_path,
        experiment_id="exp-sparse",
        run_id="run-s",
        with_metrics=False,
        with_equity=False,
    )
    client = _client_for(tmp_path, monkeypatch)
    try:
        response = client.get("/api/v1/research/experiments/exp-sparse")
        assert response.status_code == 200
        body = response.json()
        assert body["metrics"]["net_pnl"] == "Nicht verfügbar"
        assert body["equity"] == []
        assert body["artifacts"]["has_metrics"] is False
        assert body["integrity"]["ok"] is True
    finally:
        app.dependency_overrides.pop(get_research_service, None)


def test_corrupt_optional_metrics(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_run(
        tmp_path,
        experiment_id="exp-corrupt",
        run_id="run-c",
        corrupt_metrics=True,
    )
    client = _client_for(tmp_path, monkeypatch)
    try:
        response = client.get("/api/v1/research/experiments/exp-corrupt")
        assert response.status_code == 200
        body = response.json()
        assert body["metrics"]["net_pnl"] == "Nicht verfügbar"
        assert body["artifacts"]["has_metrics"] is False
        assert body["integrity"]["ok"] is True
    finally:
        app.dependency_overrides.pop(get_research_service, None)


def test_tampered_complete_run_hides_metrics(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run_dir = _write_run(tmp_path, experiment_id="exp-tamper", run_id="run-t")
    # Mutate sealed artifact without updating registry checksums.
    (run_dir / "metrics.json").write_text(
        json.dumps({"net_pnl": "999999", "status": "ok"}, sort_keys=True),
        encoding="utf-8",
    )
    client = _client_for(tmp_path, monkeypatch)
    try:
        listed = client.get("/api/v1/research/experiments").json()["items"]
        row = next(i for i in listed if i["experiment_id"] == "exp-tamper")
        assert row["integrity_ok"] is False
        assert row["net_pnl"] is None
        assert "checksum" in (row["integrity_error"] or "").lower() or row[
            "integrity_error"
        ]

        detail = client.get("/api/v1/research/experiments/exp-tamper")
        assert detail.status_code == 200
        body = detail.json()
        assert body["integrity"]["ok"] is False
        assert body["metrics"]["net_pnl"] == "Nicht verfügbar"
        assert body["equity"] == []
        assert "999999" not in json.dumps(body)
    finally:
        app.dependency_overrides.pop(get_research_service, None)


def test_fake_checksum_complete_not_trusted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_run(
        tmp_path,
        experiment_id="exp-fake",
        run_id="run-f",
        checksums_override={"metrics.json": "deadbeef"},
    )
    client = _client_for(tmp_path, monkeypatch)
    try:
        body = client.get("/api/v1/research/experiments/exp-fake").json()
        assert body["integrity"]["ok"] is False
        assert body["metrics"]["net_pnl"] == "Nicht verfügbar"
    finally:
        app.dependency_overrides.pop(get_research_service, None)


def test_non_finite_equity_rows_skipped(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_run(
        tmp_path,
        experiment_id="exp-eq",
        run_id="run-eq",
        equity_payload=[
            {"time": "2024-01-01T00:00:00Z", "equity": "100000"},
            {"time": "2024-01-02T00:00:00Z", "equity": "NaN"},
            {"time": "2024-01-03T00:00:00Z", "equity": "Infinity"},
            {"time": "2024-01-04T00:00:00Z", "equity": "-Infinity"},
            {"time": "2024-01-05T00:00:00Z", "equity": "not-a-number"},
            {"time": "2024-01-06T00:00:00Z", "equity": "110000"},
        ],
    )
    client = _client_for(tmp_path, monkeypatch)
    try:
        body = client.get("/api/v1/research/experiments/exp-eq").json()
        assert body["integrity"]["ok"] is True
        assert [p["equity"] for p in body["equity"]] == [100000.0, 110000.0]
        assert len(body["drawdown"]) == 2
        # Response must be JSON-serializable (no NaN/Infinity).
        json.dumps(body)
    finally:
        app.dependency_overrides.pop(get_research_service, None)


def test_path_traversal_rejected(research_client: TestClient) -> None:
    response = research_client.get(
        "/api/v1/research/experiments/../../etc/passwd"
    )
    assert response.status_code in {400, 404}


def test_artifact_path_escape_controlled(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    outside = tmp_path / "outside-run"
    outside.mkdir()
    (outside / "experiment.json").write_text("{}", encoding="utf-8")
    _write_run(
        tmp_path,
        experiment_id="exp-escape",
        run_id="run-e",
        artifact_path_override=str(outside),
    )

    client = _client_for(tmp_path, monkeypatch)
    try:
        listed = client.get("/api/v1/research/experiments").json()["items"]
        row = next(i for i in listed if i["experiment_id"] == "exp-escape")
        assert row["net_pnl"] is None
        assert row["integrity_ok"] is False
        detail = client.get("/api/v1/research/experiments/exp-escape")
        assert detail.status_code == 400
    finally:
        app.dependency_overrides.pop(get_research_service, None)


def test_research_rejects_post(research_client: TestClient) -> None:
    response = research_client.post("/api/v1/research/overview")
    assert response.status_code == 405
