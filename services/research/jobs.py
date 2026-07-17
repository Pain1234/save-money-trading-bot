"""Filesystem-backed research job status (Issue #242 / P4.6).

V1: jobs persist under ``artifacts/research/jobs/``. Execution uses an in-process
thread (no Celery/Redis). After a process restart, ``queued`` / ``running`` jobs
without a live thread are marked failed on the next status read (documented V1
limit).
"""

from __future__ import annotations

import json
import os
import threading
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

JobStatus = Literal["created", "queued", "running", "completed", "failed"]
TerminalStatus = frozenset({"completed", "failed"})

_ACTIVE_LOCK = threading.Lock()
_ACTIVE_THREADS: dict[str, threading.Thread] = {}
_EXPERIMENT_LOCKS_GUARD = threading.Lock()
_EXPERIMENT_LOCKS: dict[str, threading.RLock] = {}


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


def _parse_utc(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)


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
        )


class ResearchJobStore:
    """Job file store with per-experiment locks and atomic JSON writes."""

    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self.jobs_dir = self.root / "artifacts" / "research" / "jobs"
        self.pending_dir = self.root / "artifacts" / "research" / "pending"

    def _job_path(self, experiment_id: str) -> Path:
        return self.jobs_dir / f"{experiment_id}.json"

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
        """Fail closed for orphaned queued/running jobs after restart."""
        if job.status not in {"queued", "running"}:
            return job
        with self.lock_for(job.experiment_id):
            current = self._read_unlocked(job.experiment_id)
            if current is None:
                return job
            if current.status not in {"queued", "running"}:
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
