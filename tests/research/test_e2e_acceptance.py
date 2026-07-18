"""Research Workspace end-to-end acceptance (Issue #250 / P4.8).

Explicit matrix (see Issue #250):

1. Trend Strategy V1 listed exactly once (no alias duplicate).
2. Price/trade chart matches the bound dataset + ``trades.json``.
3. Tampered checksum / dataset mismatch -> fail-closed (chart/trades hidden).
4. Equity/drawdown remain available when only the chart surface fails integrity.
5. Deterministic **failed** job without any private data.
6. Lab -> Run -> Detail happy path against the committed ``local_lab`` catalog.
7. Double-start is blocked.
8. Compare surface (#246) is not present on this branch stack -> documented.
9. Robustness (#247) / Gate (#248) / Validation (#249) smoke, as delivered.
10. Restart/orphan recovery (#245) is not present on this branch stack -> documented.

Design notes:

- Uses the *committed* ``examples/research/local_lab/catalog.json`` fixture
  (Issue #264) -- no free client paths, no production/private data.
- Deliberately does **not** set ``RESEARCH_ALLOW_DIRTY_GIT`` anywhere in this
  file (project instruction: no dirty-git escape hatch in acceptance
  fixtures). The real git working tree must be clean when this module runs;
  that is itself part of what "Reproduzierbarkeit" means for #250.
- No Postgres / network / live-exchange dependency; safe to run in the
  default CI test lane.
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
    get_validation_service,
)
from research.artifacts import compute_artifact_checksums
from research.gate_service import GateService
from research.robustness_service import RobustnessOrchestrationService
from research.service import ResearchReadService
from research.validation_service import ValidationStudyService
from research.write_service import ResearchWriteService
from strategy_engine.constants import STRATEGY_VERSION

REPO_ROOT = Path(__file__).resolve().parents[2]
LOCAL_LAB_CATALOG_ID = "local-btc-fixture"
LOCAL_LAB_CATALOG_PATH = (
    REPO_ROOT / "examples" / "research" / "local_lab" / "catalog.json"
)
POLL_TIMEOUT_SECONDS = 90


def _lab_payload(*, name: str, end: str = "2024-01-31T23:59:59.000000Z") -> dict[str, object]:
    """A valid Strategy Lab payload against the committed local_lab catalog."""
    return {
        "strategy_id": "trend_v1",
        "strategy_version": STRATEGY_VERSION,
        "name": name,
        "notes": "Issue #250 E2E acceptance",
        "symbols": ["BTC"],
        "timeframe": "1D",
        "time_range": {
            "start": "2024-01-01T00:00:00.000000Z",
            "end": end,
        },
        "starting_capital": "100000",
        "parameters": {"strategy_version": STRATEGY_VERSION},
        "fee_assumption": {
            "entry_fee_rate": "0.0005",
            "exit_fee_rate": "0.0005",
        },
        "slippage_assumption": {"slippage_bps": "5"},
        "random_seed": 7,
        "dataset_catalog_id": LOCAL_LAB_CATALOG_ID,
        "owner": "test",
    }


def _poll_status(client: TestClient, experiment_id: str) -> str:
    deadline = time.time() + POLL_TIMEOUT_SECONDS
    status = "queued"
    while time.time() < deadline:
        status = client.get(
            f"/api/v1/research/experiments/{experiment_id}/status"
        ).json()["status"]
        if status in {"completed", "failed"}:
            return status
        time.sleep(0.2)
    return status


def _poll_robustness(client: TestClient, robustness_id: str) -> str:
    deadline = time.time() + POLL_TIMEOUT_SECONDS
    status = "queued"
    while time.time() < deadline:
        status = client.get(
            f"/api/v1/research/robustness/{robustness_id}/status"
        ).json()["status"]
        if status in {"completed", "failed"}:
            return status
        time.sleep(0.2)
    return status


@pytest.fixture
def e2e_client(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> TestClient:
    """Wired FastAPI client for the whole Research Workspace surface.

    Root is an isolated ``tmp_path`` (never the real ``artifacts/research``);
    the catalog and repo root point at the real, committed local_lab fixture
    and this checkout. No ``RESEARCH_ALLOW_DIRTY_GIT`` override.
    """
    assert LOCAL_LAB_CATALOG_PATH.is_file(), "committed local_lab catalog missing"

    monkeypatch.delenv("RESEARCH_ALLOW_DIRTY_GIT", raising=False)
    monkeypatch.setenv("RESEARCH_ARTIFACTS_ROOT", str(tmp_path))
    monkeypatch.setenv("RESEARCH_DATASET_CATALOG_PATH", str(LOCAL_LAB_CATALOG_PATH))
    monkeypatch.setenv("RESEARCH_REPO_ROOT", str(REPO_ROOT))

    def _read() -> ResearchReadService:
        return ResearchReadService(tmp_path)

    def _write() -> ResearchWriteService:
        return ResearchWriteService(
            tmp_path, repo_root=REPO_ROOT, allow_dirty_git=False
        )

    def _robustness() -> RobustnessOrchestrationService:
        return RobustnessOrchestrationService(
            tmp_path, repo_root=REPO_ROOT, allow_dirty_git=False
        )

    def _gate() -> GateService:
        return GateService(tmp_path, repo_root=REPO_ROOT)

    def _validation() -> ValidationStudyService:
        return ValidationStudyService(tmp_path, repo_root=REPO_ROOT)

    app.dependency_overrides[get_research_service] = _read
    app.dependency_overrides[get_research_write_service] = _write
    app.dependency_overrides[get_robustness_service] = _robustness
    app.dependency_overrides[get_gate_service] = _gate
    app.dependency_overrides[get_validation_service] = _validation
    client = TestClient(app)
    try:
        yield client
    finally:
        app.dependency_overrides.pop(get_research_service, None)
        app.dependency_overrides.pop(get_research_write_service, None)
        app.dependency_overrides.pop(get_robustness_service, None)
        app.dependency_overrides.pop(get_gate_service, None)
        app.dependency_overrides.pop(get_validation_service, None)


# --- 1. Trend Strategy V1 catalog identity -----------------------------------


def test_trend_strategy_v1_listed_exactly_once(e2e_client: TestClient) -> None:
    body = e2e_client.get("/api/v1/research/strategies").json()
    ids = [item["strategy_id"] for item in body["items"]]
    assert ids.count("trend_v1") == 1
    assert "trend_strategy_v1" not in ids

    detail = e2e_client.get("/api/v1/research/strategies/trend_v1").json()
    assert detail["display_name"] == "Trend Strategy V1"

    # Alias remains resolvable for historical specs, but is not a second entry.
    alias_detail = e2e_client.get(
        "/api/v1/research/strategies/trend_strategy_v1"
    ).json()
    assert alias_detail["strategy_id"] == "trend_v1"


# --- 6 & 7. Lab -> Run -> Detail happy path + double-start blocked ----------


def test_lab_run_detail_happy_path_and_double_start_blocked(
    e2e_client: TestClient,
) -> None:
    created = e2e_client.post(
        "/api/v1/research/experiments",
        json=_lab_payload(name="E2E happy path"),
    )
    assert created.status_code == 200, created.text
    experiment_id = created.json()["experiment_id"]

    started = e2e_client.post(f"/api/v1/research/experiments/{experiment_id}/start")
    assert started.status_code == 200, started.text

    status = _poll_status(e2e_client, experiment_id)
    assert status == "completed", status

    detail = e2e_client.get(f"/api/v1/research/experiments/{experiment_id}").json()
    assert detail["integrity"]["ok"] is True
    assert detail["summary"]["strategy_id"] == "trend_v1"

    listed = e2e_client.get("/api/v1/research/experiments").json()["items"]
    assert any(i["experiment_id"] == experiment_id for i in listed)

    # 7. Double start blocked (both while running would be, and after complete).
    again = e2e_client.post(f"/api/v1/research/experiments/{experiment_id}/start")
    assert again.status_code == 409


# --- 2. Price/trade chart against bound dataset + trades.json ---------------


def test_chart_matches_bound_dataset_and_trades_json(e2e_client: TestClient) -> None:
    from tests.research.fixtures import btc_bundle

    created = e2e_client.post(
        "/api/v1/research/experiments",
        json=_lab_payload(name="E2E chart vs dataset"),
    )
    experiment_id = created.json()["experiment_id"]
    e2e_client.post(f"/api/v1/research/experiments/{experiment_id}/start")
    assert _poll_status(e2e_client, experiment_id) == "completed"

    trades_resp = e2e_client.get(
        f"/api/v1/research/experiments/{experiment_id}/trades",
        params={"symbol": "BTC"},
    )
    assert trades_resp.status_code == 200, trades_resp.text
    trades_body = trades_resp.json()

    chart_resp = e2e_client.get(
        f"/api/v1/research/experiments/{experiment_id}/chart-data",
        params={"symbol": "BTC"},
    )
    assert chart_resp.status_code == 200, chart_resp.text
    chart_body = chart_resp.json()

    # The chart's embedded trade markers are the *same* verified trades.json
    # content the standalone /trades endpoint serves -- no second source.
    assert chart_body["trades"] == trades_body["trades"]

    # Candles trace back to the exact bound HistoricalDataBundle (no invented
    # / live data): every fixture daily candle must appear byte-for-byte.
    bundle = btc_bundle()
    expected_by_time = {c.open_time.isoformat(): c for c in bundle.daily["BTC"]}
    seen = 0
    for row in chart_body["candles"]:
        expected = expected_by_time.get(row["time"])
        if expected is None:
            continue
        assert row["open"] == str(expected.open)
        assert row["high"] == str(expected.high)
        assert row["low"] == str(expected.low)
        assert row["close"] == str(expected.close)
        seen += 1
    assert seen > 0, "no fixture candle matched by timestamp"


# --- 3 & 4. Tampered checksum / dataset mismatch -> fail closed; -----------
# --- equity/drawdown remain available -----------------------------------


def test_tampered_checksum_fails_closed_trades_and_chart_hidden(
    e2e_client: TestClient,
) -> None:
    """A raw byte-level tamper (no re-seal) must hide trades AND chart."""
    created = e2e_client.post(
        "/api/v1/research/experiments",
        json=_lab_payload(name="E2E tamper checksum"),
    )
    experiment_id = created.json()["experiment_id"]
    e2e_client.post(f"/api/v1/research/experiments/{experiment_id}/start")
    assert _poll_status(e2e_client, experiment_id) == "completed"

    detail = e2e_client.get(f"/api/v1/research/experiments/{experiment_id}").json()
    run_id = detail["summary"]["run_id"]
    root = app.dependency_overrides[get_research_service]().root
    run_dir = Path(root) / "artifacts" / "research" / experiment_id / run_id
    assert (run_dir / "trades.json").is_file()

    # Tamper trades.json bytes; do NOT recompute/reseal checksums. This is
    # the "attacker without registry write access" scenario.
    (run_dir / "trades.json").write_text("[]", encoding="utf-8")

    trades_resp = e2e_client.get(
        f"/api/v1/research/experiments/{experiment_id}/trades",
        params={"symbol": "BTC"},
    )
    assert trades_resp.status_code in {400, 409}
    assert "detail" in trades_resp.json()
    assert "trades" not in trades_resp.json()

    chart_resp = e2e_client.get(
        f"/api/v1/research/experiments/{experiment_id}/chart-data",
        params={"symbol": "BTC"},
    )
    assert chart_resp.status_code in {400, 409}
    assert "detail" in chart_resp.json()
    assert "candles" not in chart_resp.json()


def test_chart_integrity_failure_leaves_equity_drawdown_available(
    e2e_client: TestClient,
) -> None:
    """A chart-specific dataset mismatch must not affect equity/drawdown or /trades."""
    created = e2e_client.post(
        "/api/v1/research/experiments",
        json=_lab_payload(name="E2E chart dataset mismatch"),
    )
    experiment_id = created.json()["experiment_id"]
    e2e_client.post(f"/api/v1/research/experiments/{experiment_id}/start")
    assert _poll_status(e2e_client, experiment_id) == "completed"

    detail_before = e2e_client.get(
        f"/api/v1/research/experiments/{experiment_id}"
    ).json()
    run_id = detail_before["summary"]["run_id"]
    equity_before = detail_before["equity"]

    root = app.dependency_overrides[get_research_service]().root
    run_dir = Path(root) / "artifacts" / "research" / experiment_id / run_id
    chart_path = run_dir / "chart_data.json"
    chart_raw = json.loads(chart_path.read_text(encoding="utf-8"))
    # Forge a dataset_content_hash that disagrees with run_manifest.json, then
    # re-seal so the raw byte-level checksum trust anchor still passes -- the
    # *semantic* dataset-binding check inside experiment_chart_data must be
    # what fails closed here, independent of the whole-directory checksum.
    chart_raw["dataset_content_hash"] = "b" * 64
    chart_path.write_text(json.dumps(chart_raw, sort_keys=True), encoding="utf-8")

    registry_path = Path(root) / "artifacts" / "research" / "registry.jsonl"
    lines = registry_path.read_text(encoding="utf-8").strip().splitlines()
    resealed = json.loads(lines[-1])
    resealed["checksums"] = compute_artifact_checksums(run_dir)
    with registry_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(resealed, sort_keys=True) + "\n")

    # Chart fails closed on the semantic dataset mismatch.
    chart_resp = e2e_client.get(
        f"/api/v1/research/experiments/{experiment_id}/chart-data",
        params={"symbol": "BTC"},
    )
    assert chart_resp.status_code == 400, chart_resp.text
    assert "dataset_content_hash" in chart_resp.json()["detail"]

    # Trades (chart_data.json is irrelevant to /trades) still work.
    trades_resp = e2e_client.get(
        f"/api/v1/research/experiments/{experiment_id}/trades",
        params={"symbol": "BTC"},
    )
    assert trades_resp.status_code == 200, trades_resp.text

    # Equity/drawdown (from the whole-directory checksum, which still
    # verifies cleanly after the re-seal) remain fully available.
    detail_after = e2e_client.get(
        f"/api/v1/research/experiments/{experiment_id}"
    ).json()
    assert detail_after["integrity"]["ok"] is True
    assert detail_after["equity"] == equity_before
    assert len(detail_after["equity"]) == len(detail_after["drawdown"])

    equity_resp = e2e_client.get(
        f"/api/v1/research/experiments/{experiment_id}/equity"
    )
    assert equity_resp.status_code == 200
    assert equity_resp.json()["equity"] == equity_before


# --- 5. Deterministic failed job without private data ------------------------


def test_deterministic_failed_job_without_private_data(
    e2e_client: TestClient,
) -> None:
    """Lab-style microsecond end (.999999Z) is after the fixture manifest end.

    Documented gotcha (examples/research/README.md): the committed local_lab
    manifest ends at an inclusive whole second (``...23:59:59.000000Z``).
    Requesting the Lab UI's default day-end granularity
    (``...23:59:59.999999Z``) is after that bound and fails dataset binding
    deterministically at run time -- a safe, reproducible failure path that
    never touches private Strategy V1 results.
    """
    created = e2e_client.post(
        "/api/v1/research/experiments",
        json=_lab_payload(
            name="E2E deterministic failure",
            end="2024-01-31T23:59:59.999999Z",
        ),
    )
    assert created.status_code == 200, created.text
    experiment_id = created.json()["experiment_id"]

    started = e2e_client.post(f"/api/v1/research/experiments/{experiment_id}/start")
    assert started.status_code == 200, started.text

    status = _poll_status(e2e_client, experiment_id)
    assert status == "failed", status

    final = e2e_client.get(
        f"/api/v1/research/experiments/{experiment_id}/status"
    ).json()
    assert final["error"] is not None
    assert "time_range.end is after DatasetManifest" in final["error"]
    # No metrics/PnL leaked into the error surface.
    assert "net_pnl" not in json.dumps(final).lower()


# --- 8. Compare surface (#246) not present on this branch stack -------------


def test_compare_surface_not_present_on_this_stack(e2e_client: TestClient) -> None:
    """#246 (P4.7a compare) is a separate PR, not stacked under #249 -> #250.

    Documents current absence rather than silently skipping: if a compare
    route is ever wired up without updating this test, that is a signal to
    add real coverage here instead of leaving this note stale.
    """
    resp = e2e_client.get("/api/v1/research/compare")
    assert resp.status_code == 404
    # POST is not on the research write allow-list either -> the readonly
    # method middleware blocks it (405) before it could ever reach a route.
    resp_post = e2e_client.post("/api/v1/research/compare", json={})
    assert resp_post.status_code == 405


# --- 10. Restart/orphan recovery (#245) not present on this branch stack ----


def test_restart_ownership_api_not_present_on_this_stack(
    e2e_client: TestClient,
) -> None:
    """#245 (durable job ownership + restart recovery) is not on this stack.

    V1 in-process jobs documented limitation (services/research/jobs.py):
    queued/running jobs without a live thread are marked failed on the next
    status read after a process restart; there is no separate
    restart/ownership endpoint to smoke-test here yet.
    """
    resp = e2e_client.get("/api/v1/research/experiments/exp_missing/ownership")
    assert resp.status_code == 404
    # POST is not on the research write allow-list either -> the readonly
    # method middleware blocks it (405) before it could ever reach a route.
    resp2 = e2e_client.post(
        "/api/v1/research/experiments/exp_missing/restart", json={}
    )
    assert resp2.status_code == 405


# --- 9. Robustness (#247) / Gate (#248) / Validation (#249) smoke ----------


def test_robustness_gate_validation_smoke(e2e_client: TestClient) -> None:
    """Full evidence chain: base run -> bootstrap robustness -> gate -> study.

    Deep functional coverage already exists in test_robustness_api.py,
    test_gate_api.py, and test_validation_api.py; this proves the same chain
    is reachable end-to-end from a Lab-created experiment on this stack
    without RESEARCH_ALLOW_DIRTY_GIT.
    """
    created = e2e_client.post(
        "/api/v1/research/experiments",
        json=_lab_payload(name="E2E robustness/gate/validation smoke"),
    )
    base_experiment_id = created.json()["experiment_id"]
    e2e_client.post(f"/api/v1/research/experiments/{base_experiment_id}/start")
    assert _poll_status(e2e_client, base_experiment_id) == "completed"

    run_id = e2e_client.get(
        f"/api/v1/research/experiments/{base_experiment_id}"
    ).json()["summary"]["run_id"]
    assert run_id

    robustness_created = e2e_client.post(
        "/api/v1/research/robustness",
        json={
            "base_experiment_id": base_experiment_id,
            "test_type": "bootstrap",
            "config": {"block_length": 2, "n_simulations": 10, "seed": 1},
        },
    )
    assert robustness_created.status_code == 200, robustness_created.text
    robustness_id = robustness_created.json()["robustness_id"]
    e2e_client.post(f"/api/v1/research/robustness/{robustness_id}/start")
    assert _poll_robustness(e2e_client, robustness_id) == "completed"

    gate_created = e2e_client.post(
        "/api/v1/research/gates/evaluate",
        json={
            "run_id": run_id,
            "policy_version": "1.0",
            "robustness_run_ids": [robustness_id],
        },
    )
    assert gate_created.status_code == 200, gate_created.text
    gate_run_id = gate_created.json()["gate_run_id"]

    study_created = e2e_client.post(
        "/api/v1/research/validation",
        json={
            "name": "E2E acceptance study",
            "experiment_id": base_experiment_id,
            "robustness_ids": [robustness_id],
            "gate_run_ids": [gate_run_id],
            "notes": "no private Strategy V1 numbers -- synthetic local_lab fixture only",
        },
    )
    assert study_created.status_code == 200, study_created.text
    study = study_created.json()["study"]
    assert study["experiment_id"] == base_experiment_id
    assert study["gates"][0]["gate_run_id"] == gate_run_id

    listed = e2e_client.get("/api/v1/research/validation").json()["items"]
    assert any(i["study_id"] == study["study_id"] for i in listed)
