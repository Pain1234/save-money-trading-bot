"""Research Workspace end-to-end acceptance (Issue #250 / P4.8).

Explicit matrix (see Issue #250):

1. Trend Strategy V1 listed exactly once (no alias duplicate).
2. Price/trade chart matches the bound dataset + ``trades.json``.
3. Tampered checksum / dataset mismatch -> fail-closed (chart/trades hidden).
4. Equity/drawdown remain available when only the chart *semantic* surface fails
   (dataset-hash mismatch with resealed checksums); whole-artifact byte tamper
   of ``chart_data.json`` / ``trades.json`` fails closed for those surfaces.
5. Create rejects Spec ``time_range`` outside DatasetManifest (#278); start
   fail-closed without private data when pending Spec is missing (#242).
6. Lab -> Run -> Detail happy path against the committed ``local_lab`` catalog.
7. Double-start is blocked.
8. Compare surface (#246 / #277): real
   ``GET /api/v1/research/experiments/compare?run_a=&run_b=`` with compatible
   and incompatible cases (must fail if Compare is missing).
9. Robustness (#247) / Gate (#248) / Validation (#249) smoke, as delivered.
10. Restart/orphan recovery (#245 / #276): real
    ``ResearchWriteService.recover_orphans`` — orphaned ``queued`` re-dispatch
    and dead ``running`` fail-closed.

Design notes:

- Uses the *committed* ``examples/research/local_lab/catalog.json`` fixture
  (Issue #264) -- no free client paths, no production/private data.
- Deliberately does **not** set ``RESEARCH_ALLOW_DIRTY_GIT`` anywhere in this
  file (project instruction: no dirty-git escape hatch in acceptance
  fixtures). Provenance is enforced with ``allow_dirty_git=False`` against an
  isolated clean ``git clone --local`` of HEAD so ambient checkout dirt from
  earlier suite steps (editable installs, unrelated writers) cannot masquerade
  as a Lab/dataset failure. The ambient porcelain is printed before setup so
  CI logs still show the contaminating paths.
- No Postgres / network / live-exchange dependency; safe to run in the
  default CI test lane.
"""

from __future__ import annotations

import io
import json
import os
import subprocess
import tarfile
import time
from datetime import UTC, datetime, timedelta
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
from research.jobs import ResearchJob, ResearchJobStore
from research.jobs import _utc_now as jobs_utc_now
from research.robustness_service import RobustnessOrchestrationService
from research.service import ResearchReadService
from research.validation_service import ValidationStudyService
from research.write_service import ResearchWriteService
from strategy_engine.constants import STRATEGY_VERSION

REPO_ROOT = Path(__file__).resolve().parents[2]
LOCAL_LAB_CATALOG_ID = "local-btc-fixture"
POLL_TIMEOUT_SECONDS = 90


def _git_porcelain(repo: Path) -> str:
    return subprocess.check_output(
        ["git", "status", "--porcelain"],
        cwd=repo,
        stderr=subprocess.DEVNULL,
        text=True,
    )


def _materialize_clean_repo_root(tmp_path: Path) -> Path:
    """Materialize committed HEAD content into a fresh, clean git repo.

    Does **not** reuse the ambient worktree (which may be dirtied by earlier
    suite steps, editable installs, or CRLF noise). ``git archive HEAD`` exports
    only committed bytes; a new repo is initialized and committed so
    ``allow_dirty_git=False`` sees a pristine tree.
    """
    clean = tmp_path / "e2e_clean_repo"
    clean.mkdir()
    archive = subprocess.check_output(
        ["git", "archive", "--format=tar", "HEAD"],
        cwd=REPO_ROOT,
        stderr=subprocess.DEVNULL,
    )
    with tarfile.open(fileobj=io.BytesIO(archive), mode="r:") as tar:
        tar.extractall(clean)

    for args in (
        ["git", "init"],
        ["git", "config", "user.email", "e2e-acceptance@test.local"],
        ["git", "config", "user.name", "e2e-acceptance"],
        ["git", "config", "core.autocrlf", "false"],
        ["git", "add", "-A"],
        ["git", "commit", "-m", "e2e clean HEAD snapshot"],
    ):
        proc = subprocess.run(
            args, cwd=clean, check=False, capture_output=True, text=True
        )
        if proc.returncode != 0:
            raise RuntimeError(
                f"failed building clean E2E repo_root ({args!r}): "
                f"{proc.stderr or proc.stdout}"
            )

    porcelain = _git_porcelain(clean)
    if porcelain.strip():
        raise RuntimeError(
            "clean E2E repo_root is unexpectedly dirty after archive snapshot:\n"
            f"{porcelain}"
        )
    return clean


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


@pytest.fixture(scope="module")
def e2e_clean_repo_root(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """One clean HEAD clone shared by all #250 E2E tests in this module."""
    return _materialize_clean_repo_root(tmp_path_factory.mktemp("e2e_clean_repo"))


@pytest.fixture
def e2e_client(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    e2e_clean_repo_root: Path,
) -> TestClient:
    """Wired FastAPI client for the whole Research Workspace surface.

    Artifacts live under an isolated ``tmp_path``. Provenance ``repo_root`` is
    a clean local clone of HEAD (never the ambient checkout). No
    ``RESEARCH_ALLOW_DIRTY_GIT`` override.
    """
    ambient_porcelain = _git_porcelain(REPO_ROOT)
    # Always emit ambient status so CI logs show contaminating writers even
    # when E2E itself is isolated to a clean clone.
    print(
        "\n[e2e#250] ambient REPO_ROOT git status --porcelain "
        f"({REPO_ROOT}):\n"
        f"{ambient_porcelain if ambient_porcelain.strip() else '(clean)'}\n",
        flush=True,
    )

    clean_root = e2e_clean_repo_root
    catalog_path = (
        clean_root / "examples" / "research" / "local_lab" / "catalog.json"
    )
    assert catalog_path.is_file(), "committed local_lab catalog missing from clean clone"

    artifacts_root = tmp_path / "artifacts"
    artifacts_root.mkdir()

    monkeypatch.delenv("RESEARCH_ALLOW_DIRTY_GIT", raising=False)
    # Clean clone has .git — resolve HEAD directly; env pins must not bypass.
    monkeypatch.delenv("RESEARCH_EVALUATION_GIT_SHA", raising=False)
    monkeypatch.delenv("RAILWAY_GIT_COMMIT_SHA", raising=False)
    monkeypatch.setenv("RESEARCH_ARTIFACTS_ROOT", str(artifacts_root))
    monkeypatch.setenv("RESEARCH_DATASET_CATALOG_PATH", str(catalog_path))
    monkeypatch.setenv("RESEARCH_REPO_ROOT", str(clean_root))

    def _read() -> ResearchReadService:
        return ResearchReadService(artifacts_root)

    def _write() -> ResearchWriteService:
        return ResearchWriteService(
            artifacts_root, repo_root=clean_root, allow_dirty_git=False
        )

    def _robustness() -> RobustnessOrchestrationService:
        return RobustnessOrchestrationService(
            artifacts_root, repo_root=clean_root, allow_dirty_git=False
        )

    def _gate() -> GateService:
        return GateService(artifacts_root, repo_root=clean_root)

    def _validation() -> ValidationStudyService:
        return ValidationStudyService(artifacts_root, repo_root=clean_root)

    app.dependency_overrides[get_research_service] = _read
    app.dependency_overrides[get_research_write_service] = _write
    app.dependency_overrides[get_robustness_service] = _robustness
    app.dependency_overrides[get_gate_service] = _gate
    app.dependency_overrides[get_validation_service] = _validation
    client = TestClient(app, headers={"X-API-Key": "research-test-key"})
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


# --- 5. Fail-closed create + deterministic failed job (no private data) ------


def test_create_rejects_time_range_outside_manifest(
    e2e_client: TestClient,
) -> None:
    """Lab-style microsecond end (.999999Z) is after the fixture manifest end.

    Documented gotcha (examples/research/README.md): the committed local_lab
    manifest ends at an inclusive whole second (``...23:59:59.000000Z``).
    Requesting the Lab UI's default day-end granularity
    (``...23:59:59.999999Z``) must fail closed at **create** (#278) — not as a
    silent queued job that only fails later.
    """
    created = e2e_client.post(
        "/api/v1/research/experiments",
        json=_lab_payload(
            name="E2E create-time time_range rejection",
            end="2024-01-31T23:59:59.999999Z",
        ),
    )
    assert created.status_code == 422, created.text
    detail = created.json()["detail"]
    assert detail["message"] == "Validierung fehlgeschlagen"
    assert "time_range" in detail["fields"]
    assert "Dataset-Fenster" in detail["fields"]["time_range"]
    # No metrics/PnL leaked into the error surface.
    assert "net_pnl" not in json.dumps(created.json()).lower()


def test_deterministic_failed_job_without_private_data(
    e2e_client: TestClient,
) -> None:
    """Missing pending Spec after create → start fail-closed without private data.

    Matches the documented #242 acceptance path: absent ``experiment.json`` must
    not enqueue a run or leak metrics/PnL.
    """
    created = e2e_client.post(
        "/api/v1/research/experiments",
        json=_lab_payload(name="E2E deterministic failure"),
    )
    assert created.status_code == 200, created.text
    experiment_id = created.json()["experiment_id"]

    artifacts_root = Path(os.environ["RESEARCH_ARTIFACTS_ROOT"])
    pending = (
        artifacts_root
        / "artifacts"
        / "research"
        / "pending"
        / experiment_id
        / "experiment.json"
    )
    assert pending.is_file(), pending
    pending.unlink()

    started = e2e_client.post(f"/api/v1/research/experiments/{experiment_id}/start")
    assert started.status_code == 409, started.text
    detail = started.json()["detail"]
    assert "fehlt" in detail["message"].lower() or "spec" in detail.get("fields", {})
    # No metrics/PnL leaked into the error surface.
    assert "net_pnl" not in json.dumps(started.json()).lower()

    status = e2e_client.get(
        f"/api/v1/research/experiments/{experiment_id}/status"
    ).json()
    assert status["status"] in {"created", "failed"}
    assert "net_pnl" not in json.dumps(status).lower()


# --- 8. Compare surface (#246 / #277) — real endpoint -----------------------


def test_compare_compatible_and_incompatible_runs(e2e_client: TestClient) -> None:
    """Exercise ``GET /api/v1/research/experiments/compare`` (#277).

    Compatible: a completed run compared to itself (empty diffs).
    Incompatible: two completed Lab runs with different Spec ``hypothesis``
    fields (Lab ``name`` maps to hypothesis).
    Must fail (404) if the Compare route is missing from this stack.
    """
    created_a = e2e_client.post(
        "/api/v1/research/experiments",
        json=_lab_payload(name="E2E compare A"),
    )
    assert created_a.status_code == 200, created_a.text
    exp_a = created_a.json()["experiment_id"]
    e2e_client.post(f"/api/v1/research/experiments/{exp_a}/start")
    assert _poll_status(e2e_client, exp_a) == "completed"
    run_a = e2e_client.get(f"/api/v1/research/experiments/{exp_a}").json()[
        "summary"
    ]["run_id"]
    assert run_a

    created_b = e2e_client.post(
        "/api/v1/research/experiments",
        json=_lab_payload(name="E2E compare B"),
    )
    assert created_b.status_code == 200, created_b.text
    exp_b = created_b.json()["experiment_id"]
    e2e_client.post(f"/api/v1/research/experiments/{exp_b}/start")
    assert _poll_status(e2e_client, exp_b) == "completed"
    run_b = e2e_client.get(f"/api/v1/research/experiments/{exp_b}").json()[
        "summary"
    ]["run_id"]
    assert run_b
    assert run_a != run_b

    # Wrong legacy path must not falsely pass as "compare present".
    assert e2e_client.get("/api/v1/research/compare").status_code == 404

    same = e2e_client.get(
        "/api/v1/research/experiments/compare",
        params={"run_a": run_a, "run_b": run_a},
    )
    assert same.status_code == 200, same.text
    same_body = same.json()
    assert same_body["compatible"] is True
    assert same_body["diffs"] == {}
    assert same_body["run_a"] == run_a
    assert same_body["run_b"] == run_a
    assert same_body["runs"]["a"]["integrity"]["ok"] is True

    diff = e2e_client.get(
        "/api/v1/research/experiments/compare",
        params={"run_a": run_a, "run_b": run_b},
    )
    assert diff.status_code == 200, diff.text
    diff_body = diff.json()
    assert diff_body["compatible"] is False
    assert "spec.hypothesis" in diff_body["diffs"]
    assert diff_body["diffs"]["spec.hypothesis"] == [
        "E2E compare A",
        "E2E compare B",
    ]
    assert diff_body["runs"]["a"]["summary"]["run_id"] == run_a
    assert diff_body["runs"]["b"]["summary"]["run_id"] == run_b


# --- 10. Restart/orphan recovery (#245 / #276) — real ownership contract ----


def test_recover_orphans_redispatches_queued_and_fails_dead_running(
    e2e_client: TestClient,
) -> None:
    """Real #245/#276 ownership: recover_orphans re-dispatches orphaned queued
    jobs and fails closed running jobs with a dead lease.

    Uses ``ResearchWriteService.recover_orphans`` (same contract the API
    lifespan hook calls) — not invented ownership/restart HTTP endpoints.
    """
    root = Path(app.dependency_overrides[get_research_service]().root)

    # --- queued orphan -> re-dispatch -> completed ---
    created = e2e_client.post(
        "/api/v1/research/experiments",
        json=_lab_payload(name="E2E orphan queued redispatch"),
    )
    assert created.status_code == 200, created.text
    queued_id = created.json()["experiment_id"]

    store = ResearchJobStore(root)

    def _to_queued_no_dispatch(job: ResearchJob) -> None:
        job.status = "queued"
        job.updated_at = jobs_utc_now()

    store.compare_and_set(
        queued_id, expected_status="created", mutate=_to_queued_no_dispatch
    )
    assert store.is_active(queued_id) is False

    write_svc = ResearchWriteService(
        root,
        repo_root=Path(os.environ["RESEARCH_REPO_ROOT"]),
        allow_dirty_git=False,
    )
    outcome = write_svc.recover_orphans()
    assert queued_id in outcome["redispatched"]
    assert queued_id not in outcome["failed_closed"]

    assert _poll_status(e2e_client, queued_id) == "completed"

    # --- running + dead lease -> fail-closed ---
    created_run = e2e_client.post(
        "/api/v1/research/experiments",
        json=_lab_payload(name="E2E orphan running fail-closed"),
    )
    assert created_run.status_code == 200, created_run.text
    running_id = created_run.json()["experiment_id"]

    past = (datetime.now(UTC) - timedelta(seconds=5)).strftime(
        "%Y-%m-%dT%H:%M:%S.%fZ"
    )
    now = jobs_utc_now()

    def _to_dead_running(job: ResearchJob) -> None:
        job.status = "running"
        job.updated_at = now
        job.started_at = now
        job.worker_id = "dead-worker"
        job.lease_id = "dead-lease"
        job.lease_expires_at = past

    store.compare_and_set(
        running_id, expected_status="created", mutate=_to_dead_running
    )

    outcome2 = write_svc.recover_orphans()
    assert running_id in outcome2["failed_closed"]
    assert running_id not in outcome2["redispatched"]

    status = e2e_client.get(
        f"/api/v1/research/experiments/{running_id}/status"
    ).json()
    assert status["status"] == "failed"
    assert status["error"] is not None
    assert "Prozessneustart" in status["error"] or "Lease" in status["error"]


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
