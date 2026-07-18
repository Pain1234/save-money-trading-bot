"""Filesystem-backed research job status (Issue #242 / P4.6, #245 / P4.6b).

Jobs persist under ``artifacts/research/jobs/``. Execution uses an in-process
thread (no Celery/Redis mandate). Multiple API processes may share the same
job store, so process-local locks alone are not a sufficient ownership
mechanism — see the cross-process claim contract below (Issue #245).

Ownership contract (Issue #245 P1):

- ``worker_id``: stable identity of a process/worker instance (one UUID
  generated once per process import — not derived from a reused PID).
- ``lease_id``: unique per claim attempt (a fresh UUID every time a job is
  claimed ``queued -> running``); distinct from ``attempt_id``, which
  identifies the run-manifest attempt produced by the backtest engine.
- Claim transitions (``queued -> running``) are guarded by an interprocess
  file lock (``msvcrt.locking`` on Windows, ``fcntl.flock`` on POSIX) around
  a read-modify-write of the job file, so two processes racing to claim the
  same job get exactly one winner.
- The owning worker renews ``lease_expires_at`` periodically while running
  (heartbeat). A lease that is not renewed in time is dead.
- Terminal writes (``completed`` / ``failed``) are conditional: they are only
  applied if the writer still owns the job's current ``worker_id`` +
  ``lease_id``; a stale/former owner cannot overwrite a job it no longer
  owns.

Restart semantics:

- ``created``: unchanged.
- ``queued`` without a live owner: re-dispatched by the startup/API recovery
  hook (``ResearchJobStore.recover_orphans`` / ``ResearchWriteService.recover_orphans``).
- ``running`` with a dead lease: failed closed with a clear reason — no
  mid-run resume in V1.
- terminal (``completed`` / ``failed``): unchanged.
"""

from __future__ import annotations

import json
import os
import sys
import threading
import time
import uuid
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Literal

if sys.platform == "win32":
    import msvcrt
else:
    import fcntl

JobStatus = Literal["created", "queued", "running", "completed", "failed"]
TerminalStatus = frozenset({"completed", "failed"})

_ACTIVE_LOCK = threading.Lock()
_ACTIVE_THREADS: dict[str, threading.Thread] = {}
_EXPERIMENT_LOCKS_GUARD = threading.Lock()
_EXPERIMENT_LOCKS: dict[str, threading.RLock] = {}

# Stable per-process worker identity (Issue #245 P1). Generated once at import
# time so a reused PID after a crash cannot be mistaken for the same worker.
_WORKER_ID = str(uuid.uuid4())


def get_worker_id() -> str:
    """Stable identity of this process/worker instance (not only PID)."""
    return _WORKER_ID


def lease_seconds_from_env() -> int:
    return int(os.environ.get("RESEARCH_JOB_LEASE_SECONDS", "45"))


def lease_heartbeat_seconds_from_env() -> int:
    return int(os.environ.get("RESEARCH_JOB_LEASE_HEARTBEAT_SECONDS", "15"))


def _stale_running_seconds() -> int:
    return int(os.environ.get("RESEARCH_JOB_STALE_SECONDS", "900"))


def _stale_queued_seconds() -> int:
    return int(os.environ.get("RESEARCH_JOB_QUEUED_STALE_SECONDS", "60"))


def _stale_running_grace_seconds() -> int:
    return int(os.environ.get("RESEARCH_JOB_RUNNING_GRACE_SECONDS", "5"))


class JobTransitionError(Exception):
    """Raised when compare-and-set status transition fails."""

    def __init__(self, message: str, *, current_status: str | None = None) -> None:
        super().__init__(message)
        self.current_status = current_status


def _utc_now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _future_iso(seconds: int) -> str:
    return (datetime.now(UTC) + timedelta(seconds=seconds)).strftime(
        "%Y-%m-%dT%H:%M:%S.%fZ"
    )


def _parse_utc(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)


def _lease_expired(lease_expires_at: str | None) -> bool:
    """Missing lease info is treated as expired (no evidence of a live owner)."""
    if not lease_expires_at:
        return True
    try:
        expires = _parse_utc(lease_expires_at)
    except ValueError:
        return True
    return datetime.now(UTC) >= expires


class _JobFileLock:
    """Interprocess advisory lock guarding one job's read-modify-write section.

    Complements the process-local ``threading.RLock`` from
    :meth:`ResearchJobStore.lock_for`: that lock only serializes threads
    within a single process, while this lock serializes across independent
    API processes sharing the same job store directory (Issue #245 P1).
    """

    _POLL_INTERVAL_SECONDS = 0.05

    def __init__(self, path: Path, *, timeout_seconds: float = 30.0) -> None:
        self._path = path
        self._timeout_seconds = timeout_seconds
        self._handle: Any = None

    def __enter__(self) -> _JobFileLock:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        handle = open(self._path, "a+b")  # noqa: SIM115 - lifetime tied to lock
        if os.fstat(handle.fileno()).st_size == 0:
            # msvcrt.locking needs at least one byte in the file to lock.
            handle.write(b"0")
            handle.flush()
        deadline = time.monotonic() + self._timeout_seconds
        while True:
            try:
                self._acquire(handle)
                self._handle = handle
                return self
            except OSError:
                if time.monotonic() >= deadline:
                    handle.close()
                    msg = f"could not acquire interprocess job lock: {self._path}"
                    raise TimeoutError(msg) from None
                time.sleep(self._POLL_INTERVAL_SECONDS)

    def __exit__(self, *_exc_info: object) -> None:
        handle = self._handle
        self._handle = None
        if handle is None:
            return
        try:
            self._release(handle)
        finally:
            handle.close()

    if sys.platform == "win32":

        @staticmethod
        def _acquire(handle: Any) -> None:
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)

        @staticmethod
        def _release(handle: Any) -> None:
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)

    else:

        @staticmethod
        def _acquire(handle: Any) -> None:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)

        @staticmethod
        def _release(handle: Any) -> None:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


@dataclass
class ResearchJob:
    experiment_id: str
    status: JobStatus
    created_at: str
    updated_at: str
    started_at: str | None = None
    finished_at: str | None = None
    run_id: str | None = None
    attempt_id: str | None = None
    error: str | None = None
    error_detail: str | None = None
    dataset_catalog_id: str | None = None
    name: str | None = None
    # Cross-process ownership contract (Issue #245 P1) — distinct from
    # ``attempt_id`` above, which is the run-manifest attempt from the engine.
    worker_id: str | None = None
    lease_id: str | None = None
    lease_expires_at: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> ResearchJob:
        return cls(
            experiment_id=str(raw["experiment_id"]),
            status=raw["status"],  # type: ignore[arg-type]
            created_at=str(raw["created_at"]),
            updated_at=str(raw["updated_at"]),
            started_at=raw.get("started_at"),
            finished_at=raw.get("finished_at"),
            run_id=raw.get("run_id"),
            attempt_id=raw.get("attempt_id"),
            error=raw.get("error"),
            error_detail=raw.get("error_detail"),
            dataset_catalog_id=raw.get("dataset_catalog_id"),
            name=raw.get("name"),
            worker_id=raw.get("worker_id"),
            lease_id=raw.get("lease_id"),
            lease_expires_at=raw.get("lease_expires_at"),
        )


class ResearchJobStore:
    """Job file store with per-experiment locks and atomic JSON writes."""

    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self.jobs_dir = self.root / "artifacts" / "research" / "jobs"
        self.pending_dir = self.root / "artifacts" / "research" / "pending"

    def _job_path(self, experiment_id: str) -> Path:
        return self.jobs_dir / f"{experiment_id}.json"

    def _lock_path(self, experiment_id: str) -> Path:
        return self.jobs_dir / f"{experiment_id}.lock"

    def pending_spec_path(self, experiment_id: str) -> Path:
        return self.pending_dir / experiment_id / "experiment.json"

    def lock_for(self, experiment_id: str) -> threading.RLock:
        with _EXPERIMENT_LOCKS_GUARD:
            lock = _EXPERIMENT_LOCKS.get(experiment_id)
            if lock is None:
                lock = threading.RLock()
                _EXPERIMENT_LOCKS[experiment_id] = lock
            return lock

    def _atomic_write(self, path: Path, payload: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(
            f".{path.name}.{os.getpid()}.{threading.get_ident()}.tmp"
        )
        data = json.dumps(payload, sort_keys=True, indent=2) + "\n"
        try:
            with tmp.open("w", encoding="utf-8") as handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp, path)
        finally:
            tmp.unlink(missing_ok=True)

    def save(self, job: ResearchJob) -> None:
        with self.lock_for(job.experiment_id):
            self._atomic_write(self._job_path(job.experiment_id), job.to_dict())

    def get(self, experiment_id: str) -> ResearchJob | None:
        with self.lock_for(experiment_id):
            return self._read_unlocked(experiment_id)

    def _read_unlocked(self, experiment_id: str) -> ResearchJob | None:
        path = self._job_path(experiment_id)
        if not path.is_file():
            return None
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        if not isinstance(raw, dict):
            return None
        return ResearchJob.from_dict(raw)

    def list_jobs(self) -> list[ResearchJob]:
        if not self.jobs_dir.is_dir():
            return []
        jobs: list[ResearchJob] = []
        for path in sorted(self.jobs_dir.glob("*.json")):
            if path.name.endswith(".tmp"):
                continue
            experiment_id = path.stem
            job = self.get(experiment_id)
            if job is not None:
                jobs.append(job)
        return jobs

    def compare_and_set(
        self,
        experiment_id: str,
        *,
        expected_status: JobStatus,
        mutate: Callable[[ResearchJob], None],
    ) -> ResearchJob:
        """Atomically apply mutate if current status matches expected_status."""
        with self.lock_for(experiment_id):
            job = self._read_unlocked(experiment_id)
            if job is None:
                raise JobTransitionError(
                    "job not found",
                    current_status=None,
                )
            if job.status != expected_status:
                raise JobTransitionError(
                    f"expected status {expected_status!r}, found {job.status!r}",
                    current_status=job.status,
                )
            mutate(job)
            self._atomic_write(self._job_path(experiment_id), job.to_dict())
            return job

    def update(
        self,
        experiment_id: str,
        mutate: Callable[[ResearchJob], None],
    ) -> ResearchJob:
        """Locked read-mutate-write for worker heartbeats / terminal updates."""
        with self.lock_for(experiment_id):
            job = self._read_unlocked(experiment_id)
            if job is None:
                raise KeyError(experiment_id)
            mutate(job)
            self._atomic_write(self._job_path(experiment_id), job.to_dict())
            return job

    def mark_stale_if_needed(self, job: ResearchJob) -> ResearchJob:
        """Live-process watchdog for orphaned queued/running jobs.

        This is the same-process defensive backstop (a worker thread died
        without the whole process crashing). It defers to a live cross-process
        lease: a ``running`` job whose lease has not expired is left alone even
        if no thread is registered for it *in this process*, since another
        worker process may legitimately own it (Issue #245 P1). Restart-time
        orphan detection (no process at all has a thread) is handled by
        :meth:`recover_orphans`, which runs once at API startup.
        """
        if job.status not in {"queued", "running"}:
            return job
        with self.lock_for(job.experiment_id):
            current = self._read_unlocked(job.experiment_id)
            if current is None:
                return job
            if current.status not in {"queued", "running"}:
                return current

            if current.status == "running" and current.lease_expires_at is not None:
                if not _lease_expired(current.lease_expires_at):
                    return current  # live lease (this or another process)
                current.status = "failed"
                current.finished_at = _utc_now()
                current.updated_at = current.finished_at
                current.error = (
                    "Research-Lauf unterbrochen (Ownership-Lease abgelaufen; "
                    "kein Wiederaufnahme möglich)."
                )
                current.error_detail = (
                    "V1 limitation: research jobs do not resume mid-run once "
                    "their ownership lease expires (Issue #245 fail-closed "
                    "contract). Create a new experiment run instead."
                )
                self._atomic_write(
                    self._job_path(current.experiment_id), current.to_dict()
                )
                return current

            with _ACTIVE_LOCK:
                thread = _ACTIVE_THREADS.get(current.experiment_id)
                alive = thread is not None and thread.is_alive()
            if alive:
                return current

            anchor = current.updated_at
            if current.status == "running":
                anchor = current.started_at or current.updated_at
            try:
                anchor_dt = _parse_utc(anchor)
            except ValueError:
                anchor_dt = datetime.now(UTC)
            age = (datetime.now(UTC) - anchor_dt).total_seconds()

            if current.status == "queued":
                if age < _stale_queued_seconds():
                    return current
                reason = (
                    "Research-Lauf blieb in queued hängen "
                    "(Prozessneustart vor Worker-Start)."
                )
            else:
                if age < _stale_running_grace_seconds():
                    return current
                if age < _stale_running_seconds() and thread is not None:
                    return current
                reason = (
                    "Research-Lauf unterbrochen "
                    "(Prozessneustart oder Worker verloren)."
                )

            current.status = "failed"
            current.finished_at = _utc_now()
            current.updated_at = current.finished_at
            current.error = reason
            current.error_detail = (
                "V1 limitation: in-process research jobs do not resume after restart. "
                "Create a new experiment (new semantic Spec) or use the CLI; "
                "explicit Retry/Re-run is not supported yet."
            )
            self._atomic_write(self._job_path(current.experiment_id), current.to_dict())
            return current

    def claim(
        self,
        experiment_id: str,
        *,
        worker_id: str,
        lease_seconds: int,
    ) -> ResearchJob:
        """Cross-process atomic claim ``queued -> running`` (Issue #245 P1).

        Guarded by an interprocess file lock so that concurrent claim attempts
        from independent API processes have exactly one winner. Succeeds only
        if the job is still ``queued`` and unclaimed (no lease) or its previous
        lease has expired.
        """
        with self.lock_for(experiment_id), _JobFileLock(self._lock_path(experiment_id)):
            job = self._read_unlocked(experiment_id)
            if job is None:
                raise JobTransitionError("job not found", current_status=None)
            if job.status != "queued":
                raise JobTransitionError(
                    f"expected status 'queued', found {job.status!r}",
                    current_status=job.status,
                )
            if job.lease_expires_at is not None and not _lease_expired(
                job.lease_expires_at
            ):
                raise JobTransitionError(
                    "job already claimed by a live worker lease",
                    current_status=job.status,
                )
            now = _utc_now()
            job.status = "running"
            job.worker_id = worker_id
            job.lease_id = str(uuid.uuid4())
            job.lease_expires_at = _future_iso(lease_seconds)
            job.started_at = now
            job.updated_at = now
            self._atomic_write(self._job_path(experiment_id), job.to_dict())
            return job

    def renew_lease(
        self,
        experiment_id: str,
        *,
        worker_id: str,
        lease_id: str,
        lease_seconds: int,
    ) -> ResearchJob:
        """Heartbeat: extend ``lease_expires_at`` while still the current owner.

        Under the same cross-process lock, also rejects renewals when
        ``lease_expires_at`` has already elapsed — a paused worker must not
        keep a lease alive after orphan recovery is entitled to reclaim it.
        """
        with self.lock_for(experiment_id), _JobFileLock(self._lock_path(experiment_id)):
            job = self._read_unlocked(experiment_id)
            if job is None:
                raise KeyError(experiment_id)
            if job.status != "running" or job.worker_id != worker_id or job.lease_id != lease_id:
                raise JobTransitionError(
                    "lease is no longer owned by this worker/attempt",
                    current_status=job.status,
                )
            if _lease_expired(job.lease_expires_at):
                raise JobTransitionError(
                    "lease expired; refusing renewal",
                    current_status=job.status,
                )
            job.lease_expires_at = _future_iso(lease_seconds)
            job.updated_at = _utc_now()
            self._atomic_write(self._job_path(experiment_id), job.to_dict())
            return job

    def finish(
        self,
        experiment_id: str,
        *,
        worker_id: str,
        lease_id: str,
        mutate: Callable[[ResearchJob], None],
    ) -> ResearchJob:
        """Conditional terminal write (Issue #245 P1).

        Applies ``mutate`` (expected to set a terminal status) only if the
        job is not already terminal, the caller still owns its current
        ``worker_id`` + ``lease_id``, **and** the lease has not expired.
        A paused worker that lost its lease must not write ``completed``
        after orphan recovery is entitled to fail-close the job.
        """
        with self.lock_for(experiment_id), _JobFileLock(self._lock_path(experiment_id)):
            job = self._read_unlocked(experiment_id)
            if job is None:
                raise KeyError(experiment_id)
            if job.status in TerminalStatus:
                # Already terminal (e.g. failed closed by orphan recovery) —
                # never overwritten, even if worker_id/lease_id still match.
                raise JobTransitionError(
                    "job already terminal; refusing overwrite",
                    current_status=job.status,
                )
            if job.worker_id != worker_id or job.lease_id != lease_id:
                raise JobTransitionError(
                    "stale worker/lease; refusing terminal write",
                    current_status=job.status,
                )
            if _lease_expired(job.lease_expires_at):
                raise JobTransitionError(
                    "lease expired; refusing terminal write",
                    current_status=job.status,
                )
            mutate(job)
            self._atomic_write(self._job_path(experiment_id), job.to_dict())
            return job

    def recover_orphans(self) -> list[ResearchJob]:
        """Startup recovery hook (Issue #245 restart semantics).

        Intended to run exactly once per process, before the API starts
        serving research-write traffic:

        - ``queued`` jobs without a live owner are unclaimed (any stale
          worker/lease fields cleared) so the caller can re-dispatch them.
        - ``running`` jobs whose lease is dead (expired or missing) are failed
          closed — V1 does not resume mid-run. ``running`` jobs with a live
          lease (owned by a still-alive worker, possibly in another process)
          are left untouched.

        Safe to call from multiple processes concurrently: the interprocess
        lock serializes each job's read-modify-write, and any later claim
        attempt on a re-queued job still goes through :meth:`claim`, so at
        most one process ends up actually running it.
        """
        changed: list[ResearchJob] = []
        for job in self.list_jobs():
            if job.status not in {"queued", "running"}:
                continue
            with self.lock_for(job.experiment_id), _JobFileLock(
                self._lock_path(job.experiment_id)
            ):
                current = self._read_unlocked(job.experiment_id)
                if current is None or current.status not in {"queued", "running"}:
                    continue

                if current.status == "queued":
                    if current.lease_expires_at is not None and not _lease_expired(
                        current.lease_expires_at
                    ):
                        continue  # live claim in flight elsewhere; leave it
                    if current.worker_id is not None or current.lease_id is not None:
                        current.worker_id = None
                        current.lease_id = None
                        current.lease_expires_at = None
                        current.updated_at = _utc_now()
                        self._atomic_write(
                            self._job_path(current.experiment_id), current.to_dict()
                        )
                    changed.append(current)
                    continue

                # running
                if current.lease_expires_at is not None and not _lease_expired(
                    current.lease_expires_at
                ):
                    continue  # live owner elsewhere (multi-process) — leave it
                current.status = "failed"
                current.finished_at = _utc_now()
                current.updated_at = current.finished_at
                current.error = (
                    "Research-Lauf durch Prozessneustart unterbrochen "
                    "(verwaister Job, Lease abgelaufen oder fehlend)."
                )
                current.error_detail = (
                    "V1 limitation: running jobs do not resume mid-run after a "
                    "process restart. Fail-closed by design (Issue #245); "
                    "create a new experiment run instead."
                )
                self._atomic_write(
                    self._job_path(current.experiment_id), current.to_dict()
                )
                changed.append(current)
        return changed

    def register_thread(self, experiment_id: str, thread: threading.Thread) -> None:
        with _ACTIVE_LOCK:
            _ACTIVE_THREADS[experiment_id] = thread

    def clear_thread(self, experiment_id: str) -> None:
        with _ACTIVE_LOCK:
            _ACTIVE_THREADS.pop(experiment_id, None)

    def is_active(self, experiment_id: str) -> bool:
        with _ACTIVE_LOCK:
            thread = _ACTIVE_THREADS.get(experiment_id)
            return thread is not None and thread.is_alive()
