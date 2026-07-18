"""Ownership contract tests for robustness jobs (Issue #247 / #245 follow-up)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from research.jobs import _utc_now
from research.robustness_jobs import (
    RobustnessJob,
    RobustnessJobStore,
    RobustnessJobTransitionError,
)


def _queued_job(robustness_id: str) -> RobustnessJob:
    now = _utc_now()
    return RobustnessJob(
        robustness_id=robustness_id,
        base_experiment_id="exp_base",
        base_run_id="run_pinned",
        test_type="bootstrap",
        status="queued",
        created_at=now,
        updated_at=now,
        config={"block_length": 2, "n_simulations": 10, "seed": 1},
    )


def test_claim_transitions_queued_to_running(tmp_path: Path) -> None:
    store = RobustnessJobStore(tmp_path)
    store.save(_queued_job("rob_claim_ok"))

    job = store.claim("rob_claim_ok", worker_id="worker-a", lease_seconds=30)

    assert job.status == "running"
    assert job.worker_id == "worker-a"
    assert job.lease_id is not None
    assert job.lease_expires_at is not None
    assert job.base_run_id == "run_pinned"


def test_claim_rejects_already_claimed_live_lease(tmp_path: Path) -> None:
    store = RobustnessJobStore(tmp_path)
    store.save(_queued_job("rob_claimed_twice"))
    store.claim("rob_claimed_twice", worker_id="worker-a", lease_seconds=30)

    with pytest.raises(RobustnessJobTransitionError):
        store.claim("rob_claimed_twice", worker_id="worker-b", lease_seconds=30)


def test_renew_and_finish_reject_expired_lease(tmp_path: Path) -> None:
    store = RobustnessJobStore(tmp_path)
    store.save(_queued_job("rob_expired_owner"))
    job = store.claim("rob_expired_owner", worker_id="worker-a", lease_seconds=30)

    def _expire(j: RobustnessJob) -> None:
        j.lease_expires_at = (datetime.now(UTC) - timedelta(seconds=1)).strftime(
            "%Y-%m-%dT%H:%M:%S.%fZ"
        )

    store.update("rob_expired_owner", _expire)

    with pytest.raises(RobustnessJobTransitionError, match="lease expired"):
        store.renew_lease(
            "rob_expired_owner",
            worker_id="worker-a",
            lease_id=job.lease_id or "",
            lease_seconds=30,
        )
    with pytest.raises(RobustnessJobTransitionError, match="lease expired"):
        store.finish(
            "rob_expired_owner",
            worker_id="worker-a",
            lease_id=job.lease_id or "",
            mutate=lambda j: setattr(j, "status", "completed"),
        )


def test_finish_rejects_stale_owner(tmp_path: Path) -> None:
    store = RobustnessJobStore(tmp_path)
    store.save(_queued_job("rob_finish"))
    job = store.claim("rob_finish", worker_id="worker-a", lease_seconds=30)

    with pytest.raises(RobustnessJobTransitionError, match="stale"):
        store.finish(
            "rob_finish",
            worker_id="worker-a",
            lease_id="not-the-real-lease",
            mutate=lambda j: setattr(j, "status", "completed"),
        )

    def _complete(j: RobustnessJob) -> None:
        j.status = "completed"
        j.finished_at = _utc_now()
        j.updated_at = j.finished_at

    finished = store.finish(
        "rob_finish",
        worker_id="worker-a",
        lease_id=job.lease_id or "",
        mutate=_complete,
    )
    assert finished.status == "completed"


def test_recover_orphans_fails_dead_running_lease(tmp_path: Path) -> None:
    store = RobustnessJobStore(tmp_path)
    now = _utc_now()
    store.save(
        RobustnessJob(
            robustness_id="rob_dead_running",
            base_experiment_id="exp_base",
            base_run_id="run_pinned",
            test_type="bootstrap",
            status="running",
            created_at=now,
            updated_at=now,
            started_at=now,
            worker_id="dead-worker",
            lease_id="dead-lease",
            lease_expires_at=(datetime.now(UTC) - timedelta(seconds=5)).strftime(
                "%Y-%m-%dT%H:%M:%S.%fZ"
            ),
            config={},
        )
    )

    changed = store.recover_orphans()
    assert len(changed) == 1
    assert changed[0].status == "failed"
    assert "Prozessneustart" in (changed[0].error or "")


def test_recover_orphans_unclaims_stale_queued_job(tmp_path: Path) -> None:
    store = RobustnessJobStore(tmp_path)
    now = _utc_now()
    store.save(
        RobustnessJob(
            robustness_id="rob_stale_queued",
            base_experiment_id="exp_base",
            base_run_id="run_pinned",
            test_type="bootstrap",
            status="queued",
            created_at=now,
            updated_at=now,
            worker_id="old-worker",
            lease_id="old-lease",
            lease_expires_at=(datetime.now(UTC) - timedelta(seconds=5)).strftime(
                "%Y-%m-%dT%H:%M:%S.%fZ"
            ),
            config={},
        )
    )

    changed = store.recover_orphans()
    assert len(changed) == 1
    assert changed[0].status == "queued"
    assert changed[0].worker_id is None
    assert changed[0].lease_id is None
    assert changed[0].lease_expires_at is None
