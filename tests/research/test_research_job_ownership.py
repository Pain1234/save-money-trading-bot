"""Tests for the cross-process research job ownership contract (Issue #245).

Covers: cross-process atomic claim (exactly one winner), conditional
terminal writes (stale worker/lease rejected), lease-expiry orphan handling,
and queued re-dispatch after a simulated API process restart.
"""

from __future__ import annotations

import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from research.jobs import (
    JobTransitionError,
    ResearchJob,
    ResearchJobStore,
    _utc_now,
    get_worker_id,
    lease_seconds_from_env,
)

from tests.research.test_research_write_api import (  # noqa: F401 - fixture reuse
    REPO_ROOT,
    write_client,
)


def _queued_job(experiment_id: str) -> ResearchJob:
    now = _utc_now()
    return ResearchJob(
        experiment_id=experiment_id,
        status="queued",
        created_at=now,
        updated_at=now,
    )


def test_get_worker_id_is_stable_within_process() -> None:
    assert get_worker_id() == get_worker_id()
    assert isinstance(get_worker_id(), str)
    assert len(get_worker_id()) > 0


def test_claim_transitions_queued_to_running(tmp_path: Path) -> None:
    store = ResearchJobStore(tmp_path)
    store.save(_queued_job("exp_claim_ok"))

    job = store.claim("exp_claim_ok", worker_id="worker-a", lease_seconds=30)

    assert job.status == "running"
    assert job.worker_id == "worker-a"
    assert job.lease_id is not None
    assert job.lease_expires_at is not None
    assert job.started_at is not None


def test_claim_rejects_non_queued_job(tmp_path: Path) -> None:
    store = ResearchJobStore(tmp_path)
    now = _utc_now()
    store.save(
        ResearchJob(
            experiment_id="exp_created",
            status="created",
            created_at=now,
            updated_at=now,
        )
    )
    with pytest.raises(JobTransitionError):
        store.claim("exp_created", worker_id="worker-a", lease_seconds=30)


def test_claim_rejects_already_claimed_live_lease(tmp_path: Path) -> None:
    store = ResearchJobStore(tmp_path)
    store.save(_queued_job("exp_claimed_twice"))
    store.claim("exp_claimed_twice", worker_id="worker-a", lease_seconds=30)

    with pytest.raises(JobTransitionError):
        store.claim("exp_claimed_twice", worker_id="worker-b", lease_seconds=30)


def test_claim_allows_reclaim_after_lease_expiry(tmp_path: Path) -> None:
    """A dead lease (e.g. a crashed claimant) does not permanently block a job.

    Note: production restart-recovery fails a dead-lease *running* job closed
    (no mid-run resume) rather than reclaiming it. This only exercises the
    store-level guard in isolation.
    """
    store = ResearchJobStore(tmp_path)
    store.save(_queued_job("exp_expired_lease"))
    job = store.claim("exp_expired_lease", worker_id="worker-a", lease_seconds=30)

    # Simulate a dead lease by forcing it back to queued with an expired lease,
    # as recover_orphans would leave a queued job before re-dispatch.
    def _force_expired(j: ResearchJob) -> None:
        j.status = "queued"
        j.lease_expires_at = (datetime.now(UTC) - timedelta(seconds=1)).strftime(
            "%Y-%m-%dT%H:%M:%S.%fZ"
        )

    store.update("exp_expired_lease", _force_expired)
    reclaimed = store.claim("exp_expired_lease", worker_id="worker-b", lease_seconds=30)
    assert reclaimed.worker_id == "worker-b"
    assert reclaimed.lease_id != job.lease_id


def test_two_concurrent_claim_attempts_exactly_one_winner(tmp_path: Path) -> None:
    """Same-process proxy for the cross-process claim race (P1 contract)."""
    from concurrent.futures import ThreadPoolExecutor

    store = ResearchJobStore(tmp_path)
    store.save(_queued_job("exp_race"))

    def _try_claim(worker_id: str) -> str:
        try:
            store.claim("exp_race", worker_id=worker_id, lease_seconds=30)
            return "won"
        except JobTransitionError:
            return "lost"

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = sorted(
            pool.map(_try_claim, ["worker-a", "worker-b"])
        )

    assert outcomes == ["lost", "won"]
    final = store.get("exp_race")
    assert final is not None
    assert final.status == "running"
    assert final.worker_id in {"worker-a", "worker-b"}


def _claim_in_subprocess(root: str, experiment_id: str, worker_id: str, result_path: str) -> None:
    """Top-level (picklable) target for a real separate OS process claim attempt."""
    from research.jobs import JobTransitionError, ResearchJobStore

    store = ResearchJobStore(Path(root))
    try:
        store.claim(experiment_id, worker_id=worker_id, lease_seconds=30)
        outcome = "won"
    except JobTransitionError:
        outcome = "lost"
    Path(result_path).write_text(outcome, encoding="utf-8")


def test_cross_process_claim_exactly_one_winner(tmp_path: Path) -> None:
    """Real, separate-OS-process proof of the P1 interprocess claim contract."""
    import multiprocessing

    store = ResearchJobStore(tmp_path)
    store.save(_queued_job("exp_cross_process"))

    result_a = tmp_path / "result_a.txt"
    result_b = tmp_path / "result_b.txt"
    proc_a = multiprocessing.Process(
        target=_claim_in_subprocess,
        args=(str(tmp_path), "exp_cross_process", "worker-proc-a", str(result_a)),
    )
    proc_b = multiprocessing.Process(
        target=_claim_in_subprocess,
        args=(str(tmp_path), "exp_cross_process", "worker-proc-b", str(result_b)),
    )
    proc_a.start()
    proc_b.start()
    proc_a.join(timeout=60)
    proc_b.join(timeout=60)
    assert proc_a.exitcode == 0
    assert proc_b.exitcode == 0

    outcomes = sorted([result_a.read_text(encoding="utf-8"), result_b.read_text(encoding="utf-8")])
    assert outcomes == ["lost", "won"]

    final = store.get("exp_cross_process")
    assert final is not None
    assert final.status == "running"


def test_renew_lease_requires_current_owner(tmp_path: Path) -> None:
    store = ResearchJobStore(tmp_path)
    store.save(_queued_job("exp_renew"))
    job = store.claim("exp_renew", worker_id="worker-a", lease_seconds=5)

    renewed = store.renew_lease(
        "exp_renew", worker_id="worker-a", lease_id=job.lease_id, lease_seconds=60
    )
    assert renewed.lease_expires_at is not None
    assert renewed.lease_expires_at > job.lease_expires_at

    with pytest.raises(JobTransitionError):
        store.renew_lease(
            "exp_renew", worker_id="worker-a", lease_id="wrong-lease", lease_seconds=60
        )
    with pytest.raises(JobTransitionError):
        store.renew_lease(
            "exp_renew", worker_id="worker-b", lease_id=job.lease_id, lease_seconds=60
        )


def test_finish_rejects_stale_worker_and_lease(tmp_path: Path) -> None:
    store = ResearchJobStore(tmp_path)
    store.save(_queued_job("exp_finish"))
    job = store.claim("exp_finish", worker_id="worker-a", lease_seconds=30)

    with pytest.raises(JobTransitionError):
        store.finish(
            "exp_finish",
            worker_id="worker-a",
            lease_id="not-the-real-lease",
            mutate=lambda j: setattr(j, "status", "failed"),
        )
    with pytest.raises(JobTransitionError):
        store.finish(
            "exp_finish",
            worker_id="a-different-worker",
            lease_id=job.lease_id,
            mutate=lambda j: setattr(j, "status", "failed"),
        )

    # Job is untouched by the rejected stale writes.
    assert store.get("exp_finish").status == "running"

    # The real owner (matching worker_id + lease_id) may finish it.
    store.finish(
        "exp_finish",
        worker_id="worker-a",
        lease_id=job.lease_id,
        mutate=lambda j: setattr(j, "status", "completed"),
    )
    assert store.get("exp_finish").status == "completed"


def test_renew_and_finish_reject_expired_lease(tmp_path: Path) -> None:
    """Paused worker must not renew/finish after lease_expires_at elapsed."""
    store = ResearchJobStore(tmp_path)
    store.save(_queued_job("exp_expired_owner"))
    job = store.claim("exp_expired_owner", worker_id="worker-a", lease_seconds=30)

    past = (datetime.now(UTC) - timedelta(seconds=1)).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    store.update(
        "exp_expired_owner",
        lambda j: setattr(j, "lease_expires_at", past),
    )

    with pytest.raises(JobTransitionError, match="lease expired"):
        store.renew_lease(
            "exp_expired_owner",
            worker_id="worker-a",
            lease_id=job.lease_id,
            lease_seconds=60,
        )
    with pytest.raises(JobTransitionError, match="lease expired"):
        store.finish(
            "exp_expired_owner",
            worker_id="worker-a",
            lease_id=job.lease_id,
            mutate=lambda j: setattr(j, "status", "completed"),
        )
    assert store.get("exp_expired_owner").status == "running"


def test_finish_rejects_write_after_orphan_recovery_reassigned_job(tmp_path: Path) -> None:
    """A worker that lost its lease to recovery must not resurrect the job."""
    store = ResearchJobStore(tmp_path)
    store.save(_queued_job("exp_lost_to_recovery"))
    job = store.claim("exp_lost_to_recovery", worker_id="worker-a", lease_seconds=30)

    # Force the lease to appear dead, then run orphan recovery (simulated restart).
    store.update(
        "exp_lost_to_recovery",
        lambda j: setattr(
            j,
            "lease_expires_at",
            (datetime.now(UTC) - timedelta(seconds=1)).strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
        ),
    )
    changed = store.recover_orphans()
    assert len(changed) == 1
    assert changed[0].status == "failed"

    # The original (now stale) worker must not be able to overwrite the
    # fail-closed terminal state.
    with pytest.raises(JobTransitionError):
        store.finish(
            "exp_lost_to_recovery",
            worker_id="worker-a",
            lease_id=job.lease_id,
            mutate=lambda j: setattr(j, "status", "completed"),
        )
    assert store.get("exp_lost_to_recovery").status == "failed"


def test_recover_orphans_fails_dead_running_lease(tmp_path: Path) -> None:
    store = ResearchJobStore(tmp_path)
    now = _utc_now()
    past = (datetime.now(UTC) - timedelta(seconds=5)).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    store.save(
        ResearchJob(
            experiment_id="exp_dead_lease",
            status="running",
            created_at=now,
            updated_at=now,
            started_at=now,
            worker_id="dead-worker",
            lease_id="dead-lease",
            lease_expires_at=past,
        )
    )

    changed = store.recover_orphans()

    assert len(changed) == 1
    assert changed[0].experiment_id == "exp_dead_lease"
    assert changed[0].status == "failed"
    assert changed[0].error is not None
    assert changed[0].finished_at is not None


def test_recover_orphans_leaves_live_lease_running_job_alone(tmp_path: Path) -> None:
    """Simulates a still-alive *other* process owning the running job."""
    store = ResearchJobStore(tmp_path)
    now = _utc_now()
    future = (datetime.now(UTC) + timedelta(seconds=60)).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    store.save(
        ResearchJob(
            experiment_id="exp_live_elsewhere",
            status="running",
            created_at=now,
            updated_at=now,
            started_at=now,
            worker_id="other-process-worker",
            lease_id="other-lease",
            lease_expires_at=future,
        )
    )

    changed = store.recover_orphans()

    assert changed == []
    job = store.get("exp_live_elsewhere")
    assert job is not None
    assert job.status == "running"
    assert job.worker_id == "other-process-worker"


def test_recover_orphans_unclaims_stale_queued_job(tmp_path: Path) -> None:
    store = ResearchJobStore(tmp_path)
    store.save(_queued_job("exp_orphan_queued"))

    changed = store.recover_orphans()

    assert len(changed) == 1
    assert changed[0].experiment_id == "exp_orphan_queued"
    assert changed[0].status == "queued"
    assert changed[0].worker_id is None
    assert changed[0].lease_id is None


def test_recover_orphans_ignores_terminal_and_created_jobs(tmp_path: Path) -> None:
    store = ResearchJobStore(tmp_path)
    now = _utc_now()
    store.save(
        ResearchJob(experiment_id="exp_created", status="created", created_at=now, updated_at=now)
    )
    store.save(
        ResearchJob(
            experiment_id="exp_completed", status="completed", created_at=now, updated_at=now
        )
    )

    changed = store.recover_orphans()

    assert changed == []


def test_mark_stale_if_needed_respects_live_lease_for_running_job(tmp_path: Path) -> None:
    """Same-process watchdog must not fail a job actually owned elsewhere."""
    store = ResearchJobStore(tmp_path)
    now = _utc_now()
    future = (datetime.now(UTC) + timedelta(seconds=60)).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    job = ResearchJob(
        experiment_id="exp_watchdog_live",
        status="running",
        created_at=now,
        updated_at=now,
        started_at=now,
        worker_id="other-process-worker",
        lease_id="other-lease",
        lease_expires_at=future,
    )
    store.save(job)

    result = store.mark_stale_if_needed(job)

    assert result.status == "running"


def test_mark_stale_if_needed_fails_closed_on_dead_lease(tmp_path: Path) -> None:
    store = ResearchJobStore(tmp_path)
    now = _utc_now()
    past = (datetime.now(UTC) - timedelta(seconds=5)).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    job = ResearchJob(
        experiment_id="exp_watchdog_dead",
        status="running",
        created_at=now,
        updated_at=now,
        started_at=now,
        worker_id="dead-worker",
        lease_id="dead-lease",
        lease_expires_at=past,
    )
    store.save(job)

    result = store.mark_stale_if_needed(job)

    assert result.status == "failed"


def test_lease_seconds_from_env_default_and_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("RESEARCH_JOB_LEASE_SECONDS", raising=False)
    assert lease_seconds_from_env() == 45
    monkeypatch.setenv("RESEARCH_JOB_LEASE_SECONDS", "10")
    assert lease_seconds_from_env() == 10


def test_recover_orphans_redispatches_queued_after_simulated_restart(
    tmp_path: Path,
    write_client: tuple[object, dict[str, object]],  # noqa: F811 - pytest fixture reuse
) -> None:
    """End-to-end: a job stuck in ``queued`` (as if the process crashed right
    after enqueueing, before any worker thread ever claimed it) is
    re-dispatched by the startup recovery hook and runs to completion.
    """
    from research.jobs import ResearchJobStore
    from research.jobs import _utc_now as jobs_utc_now
    from research.write_service import ResearchWriteService

    client, payload = write_client
    created = client.post("/api/v1/research/experiments", json=payload).json()
    experiment_id = created["experiment_id"]

    store = ResearchJobStore(tmp_path)

    def _to_queued_no_dispatch(job: ResearchJob) -> None:
        job.status = "queued"
        job.updated_at = jobs_utc_now()

    store.compare_and_set(
        experiment_id, expected_status="created", mutate=_to_queued_no_dispatch
    )
    assert store.is_active(experiment_id) is False

    write_svc = ResearchWriteService(tmp_path, repo_root=REPO_ROOT, allow_dirty_git=True)
    outcome = write_svc.recover_orphans()
    assert experiment_id in outcome["redispatched"]
    assert outcome["failed_closed"] == []

    deadline = time.time() + 60
    final_status = None
    status_body: dict[str, object] = {}
    while time.time() < deadline:
        status_body = client.get(
            f"/api/v1/research/experiments/{experiment_id}/status"
        ).json()
        final_status = status_body["status"]
        if final_status in {"completed", "failed"}:
            break
        time.sleep(0.2)

    assert final_status == "completed", status_body


def test_recover_orphans_fails_running_job_with_dead_lease_via_api(
    tmp_path: Path,
    write_client: tuple[object, dict[str, object]],  # noqa: F811 - pytest fixture reuse
) -> None:
    """A job left ``running`` with a dead lease (simulated crash mid-run) is
    reported as ``failed`` after recovery — no mid-run resume in V1.
    """
    from research.jobs import ResearchJobStore
    from research.write_service import ResearchWriteService

    client, payload = write_client
    created = client.post("/api/v1/research/experiments", json=payload).json()
    experiment_id = created["experiment_id"]

    store = ResearchJobStore(tmp_path)

    def _to_queued_no_dispatch(job: ResearchJob) -> None:
        job.status = "queued"
        job.updated_at = _utc_now()

    store.compare_and_set(
        experiment_id, expected_status="created", mutate=_to_queued_no_dispatch
    )
    job = store.claim(experiment_id, worker_id="crashed-worker", lease_seconds=1)
    time.sleep(1.2)  # let the lease die
    assert job.status == "running"

    write_svc = ResearchWriteService(tmp_path, repo_root=REPO_ROOT, allow_dirty_git=True)
    outcome = write_svc.recover_orphans()
    assert experiment_id in outcome["failed_closed"]

    status_body = client.get(
        f"/api/v1/research/experiments/{experiment_id}/status"
    ).json()
    assert status_body["status"] == "failed"
    assert status_body["error"] is not None
