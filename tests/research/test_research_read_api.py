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
                "dataset_id": "ds-fixture",
                "dataset_content_hash": "a" * 64,
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

    (run_dir / "trades.json").write_text(
        json.dumps(
            [
                {
                    "symbol": "BTC",
                    "signal_time": "2024-01-10T23:59:59Z",
                    "entry_time": "2024-01-11T00:00:00Z",
                    "entry_fill_price": "42000",
                    "entry_reference_price": "41900",
                    "entry_type": "BREAKOUT",
                    "quantity": "0.1",
                    "initial_stop": "40000",
                    "exit_time": "2024-01-20T00:00:00Z",
                    "exit_fill_price": "43000",
                    "exit_reason": "RC_EXIT_STOP_TRAILING",
                    "gross_pnl": "100",
                    "fees": "5",
                    "funding": "0",
                    "slippage_cost": "2",
                    "net_pnl": "93",
                    "r_multiple": "0.5",
                    "holding_period_days": 9,
                    "strategy_reason_codes": ["RC_ENTRY_BREAKOUT_20D"],
                    "trailing_stop_history": [
                        {
                            "time": "2024-01-12T00:00:00Z",
                            "trail_stop": "40500",
                            "effective_stop": "40500",
                        }
                    ],
                }
            ]
        ),
        encoding="utf-8",
    )
    (run_dir / "chart_data.json").write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "dataset_id": "ds-fixture",
                "dataset_content_hash": "a" * 64,
                "timeframe": "1D",
                "symbols": {
                    "BTC": [
                        {
                            "time": "2024-01-11T00:00:00Z",
                            "open": "41000",
                            "high": "42500",
                            "low": "40500",
                            "close": "42000",
                            "volume": "10",
                        },
                        {
                            "time": "2024-01-12T00:00:00Z",
                            "open": "42000",
                            "high": "43000",
                            "low": "41500",
                            "close": "42800",
                            "volume": "12",
                        },
                        {
                            "time": "2024-01-20T00:00:00Z",
                            "open": "42800",
                            "high": "43500",
                            "low": "42000",
                            "close": "43000",
                            "volume": "11",
                        },
                    ],
                    "ETH": [],
                },
            },
            sort_keys=True,
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


def test_trades_and_chart_data_ok(research_client: TestClient) -> None:
    trades = research_client.get("/api/v1/research/experiments/exp-alpha/trades")
    assert trades.status_code == 200
    body = trades.json()
    assert body["count"] == 1
    assert body["trades"][0]["symbol"] == "BTC"
    assert body["trades"][0]["entry_fill_price"] == "42000"

    btc = research_client.get(
        "/api/v1/research/experiments/exp-alpha/chart-data",
        params={"symbol": "BTC"},
    )
    assert btc.status_code == 200
    chart = btc.json()
    assert chart["symbol"] == "BTC"
    assert len(chart["candles"]) == 3
    assert chart["candles"][0]["close"] == "42000"
    assert len(chart["trades"]) == 1
    assert chart["trades"][0]["trailing_stop_history"][0]["effective_stop"] == "40500"


def test_trades_reject_non_complete_status(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_run(
        tmp_path,
        experiment_id="exp-failed",
        run_id="run-f",
        status="failed",
    )
    client = _client_for(tmp_path, monkeypatch)
    try:
        resp = client.get("/api/v1/research/experiments/exp-failed/trades")
        assert resp.status_code == 400
        assert "complete" in resp.json()["detail"].lower()
    finally:
        app.dependency_overrides.pop(get_research_service, None)


def test_chart_rejects_timestamp_mismatch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run_dir = _write_run(tmp_path, experiment_id="exp-ts", run_id="run-ts")
    trades = json.loads((run_dir / "trades.json").read_text(encoding="utf-8"))
    trades[0]["entry_time"] = "2023-01-01T00:00:00Z"  # outside range + candles
    (run_dir / "trades.json").write_text(json.dumps(trades), encoding="utf-8")
    checksums = compute_artifact_checksums(run_dir)
    registry = tmp_path / "artifacts" / "research" / "registry.jsonl"
    entry = json.loads(registry.read_text(encoding="utf-8").strip().splitlines()[-1])
    entry["checksums"] = checksums
    registry.write_text(json.dumps(entry, sort_keys=True) + "\n", encoding="utf-8")

    client = _client_for(tmp_path, monkeypatch)
    try:
        resp = client.get(
            "/api/v1/research/experiments/exp-ts/chart-data",
            params={"symbol": "BTC"},
        )
        assert resp.status_code == 400
        detail = resp.json()["detail"].lower()
        assert "time" in detail or "outside" in detail
    finally:
        app.dependency_overrides.pop(get_research_service, None)


def test_chart_rejects_missing_dataset_binding_fields(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run_dir = _write_run(tmp_path, experiment_id="exp-bind", run_id="run-b")
    chart = json.loads((run_dir / "chart_data.json").read_text(encoding="utf-8"))
    del chart["dataset_content_hash"]
    (run_dir / "chart_data.json").write_text(
        json.dumps(chart, sort_keys=True), encoding="utf-8"
    )
    checksums = compute_artifact_checksums(run_dir)
    registry = tmp_path / "artifacts" / "research" / "registry.jsonl"
    entry = json.loads(registry.read_text(encoding="utf-8").strip().splitlines()[-1])
    entry["checksums"] = checksums
    registry.write_text(json.dumps(entry, sort_keys=True) + "\n", encoding="utf-8")

    client = _client_for(tmp_path, monkeypatch)
    try:
        resp = client.get(
            "/api/v1/research/experiments/exp-bind/chart-data",
            params={"symbol": "BTC"},
        )
        assert resp.status_code == 400
        assert "dataset_content_hash" in resp.json()["detail"]
    finally:
        app.dependency_overrides.pop(get_research_service, None)


def test_trades_symbol_filter_and_unknown(
    research_client: TestClient,
) -> None:
    eth = research_client.get(
        "/api/v1/research/experiments/exp-alpha/trades",
        params={"symbol": "ETH"},
    )
    assert eth.status_code == 200
    assert eth.json()["count"] == 0

    bad = research_client.get(
        "/api/v1/research/experiments/exp-alpha/chart-data",
        params={"symbol": "SOL"},
    )
    assert bad.status_code == 400
    assert "symbol" in bad.json()["detail"].lower()


def test_trades_fail_closed_on_corrupt_checksum(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run_dir = _write_run(tmp_path, experiment_id="exp-corrupt", run_id="run-c")
    # Tamper trades after checksum seal.
    (run_dir / "trades.json").write_text("[]", encoding="utf-8")
    client = _client_for(tmp_path, monkeypatch)
    try:
        resp = client.get("/api/v1/research/experiments/exp-corrupt/trades")
        assert resp.status_code == 400
    finally:
        app.dependency_overrides.pop(get_research_service, None)


def test_chart_data_hash_mismatch_fail_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run_dir = _write_run(tmp_path, experiment_id="exp-hash", run_id="run-h")
    chart = json.loads((run_dir / "chart_data.json").read_text(encoding="utf-8"))
    chart["dataset_content_hash"] = "b" * 64
    (run_dir / "chart_data.json").write_text(
        json.dumps(chart, sort_keys=True), encoding="utf-8"
    )
    # Refresh trusted checksums so integrity of files passes but semantic
    # dataset binding check in chart endpoint fails.
    checksums = compute_artifact_checksums(run_dir)
    registry = tmp_path / "artifacts" / "research" / "registry.jsonl"
    lines = registry.read_text(encoding="utf-8").strip().splitlines()
    entry = json.loads(lines[-1])
    entry["checksums"] = checksums
    registry.write_text(json.dumps(entry, sort_keys=True) + "\n", encoding="utf-8")

    client = _client_for(tmp_path, monkeypatch)
    try:
        resp = client.get(
            "/api/v1/research/experiments/exp-hash/chart-data",
            params={"symbol": "BTC"},
        )
        assert resp.status_code == 400
        assert "dataset_content_hash" in resp.json()["detail"]
    finally:
        app.dependency_overrides.pop(get_research_service, None)
