"""Filesystem-backed robustness job status (Issue #247 / P4.7b).

Mirrors ``research.jobs.ResearchJobStore`` (Issue #242 pattern) for
orchestrated robustness test suites. V1 uses the same in-process thread
execution model (no Celery/Redis) and the same fail-closed stale-job
handling after a process restart: ``queued``/``running`` suites without a
live thread are marked failed on the next status read.
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

RobustnessJobStatus = Literal["created", "queued", "running", "completed", "failed"]
TERMINAL_ROBUSTNESS_STATUSES = frozenset({"completed", "failed"})

_ACTIVE_LOCK = threading.Lock()
_ACTIVE_THREADS: dict[str, threading.Thread] = {}
_JOB_LOCKS_GUARD = threading.Lock()
_JOB_LOCKS: dict[str, threading.RLock] = {}


def _utc_now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _parse_utc(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)


class RobustnessJobTransitionError(Exception):
    """Raised when compare-and-set status transition fails."""

    def __init__(self, message: str, *, current_status: str | None = None) -> None:
        super().__init__(message)
        self.current_status = current_status


@dataclass
class RobustnessJob:
    robustness_id: str
    base_experiment_id: str
    test_type: str
    status: RobustnessJobStatus
    created_at: str
    updated_at: str
    started_at: str | None = None
    finished_at: str | None = None
    error: str | None = None
    error_detail: str | None = None
    dataset_catalog_id: str | None = None
    config: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> RobustnessJob:
        return cls(
            robustness_id=str(raw["robustness_id"]),
            base_experiment_id=str(raw["base_experiment_id"]),
            test_type=str(raw["test_type"]),
            status=raw["status"],
            created_at=str(raw["created_at"]),
            updated_at=str(raw["updated_at"]),
            started_at=raw.get("started_at"),
            finished_at=raw.get("finished_at"),
            error=raw.get("error"),
            error_detail=raw.get("error_detail"),
            dataset_catalog_id=raw.get("dataset_catalog_id"),
            config=raw.get("config"),
        )


class RobustnessJobStore:
    """Job file store with per-suite locks and atomic JSON writes."""

    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self.jobs_dir = self.root / "artifacts" / "research" / "robustness" / "jobs"

    def _job_path(self, robustness_id: str) -> Path:
        return self.jobs_dir / f"{robustness_id}.json"

    def lock_for(self, robustness_id: str) -> threading.RLock:
        with _JOB_LOCKS_GUARD:
            lock = _JOB_LOCKS.get(robustness_id)
            if lock is None:
                lock = threading.RLock()
                _JOB_LOCKS[robustness_id] = lock
            return lock

    def _atomic_write(self, path: Path, payload: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(f".{path.name}.{os.getpid()}.{threading.get_ident()}.tmp")
        data = json.dumps(payload, sort_keys=True, indent=2) + "\n"
        try:
            with tmp.open("w", encoding="utf-8") as handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp, path)
        finally:
            tmp.unlink(missing_ok=True)

    def save(self, job: RobustnessJob) -> None:
        with self.lock_for(job.robustness_id):
            self._atomic_write(self._job_path(job.robustness_id), job.to_dict())

    def get(self, robustness_id: str) -> RobustnessJob | None:
        with self.lock_for(robustness_id):
            return self._read_unlocked(robustness_id)

    def _read_unlocked(self, robustness_id: str) -> RobustnessJob | None:
        path = self._job_path(robustness_id)
        if not path.is_file():
            return None
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        if not isinstance(raw, dict):
            return None
        return RobustnessJob.from_dict(raw)

    def list_jobs(self) -> list[RobustnessJob]:
        if not self.jobs_dir.is_dir():
            return []
        jobs: list[RobustnessJob] = []
        for path in sorted(self.jobs_dir.glob("*.json")):
            if path.name.endswith(".tmp"):
                continue
            job = self.get(path.stem)
            if job is not None:
                jobs.append(job)
        return jobs

    def compare_and_set(
        self,
        robustness_id: str,
        *,
        expected_status: RobustnessJobStatus,
        mutate: Callable[[RobustnessJob], None],
    ) -> RobustnessJob:
        """Atomically apply mutate if current status matches expected_status."""
        with self.lock_for(robustness_id):
            job = self._read_unlocked(robustness_id)
            if job is None:
                raise RobustnessJobTransitionError("job not found", current_status=None)
            if job.status != expected_status:
                raise RobustnessJobTransitionError(
                    f"expected status {expected_status!r}, found {job.status!r}",
                    current_status=job.status,
                )
            mutate(job)
            self._atomic_write(self._job_path(robustness_id), job.to_dict())
            return job

    def update(
        self,
        robustness_id: str,
        mutate: Callable[[RobustnessJob], None],
    ) -> RobustnessJob:
        """Locked read-mutate-write for worker heartbeats / terminal updates."""
        with self.lock_for(robustness_id):
            job = self._read_unlocked(robustness_id)
            if job is None:
                raise KeyError(robustness_id)
            mutate(job)
            self._atomic_write(self._job_path(robustness_id), job.to_dict())
            return job

    def mark_stale_if_needed(self, job: RobustnessJob) -> RobustnessJob:
        """Fail closed for orphaned queued/running suites after restart."""
        if job.status not in {"queued", "running"}:
            return job
        with self.lock_for(job.robustness_id):
            current = self._read_unlocked(job.robustness_id)
            if current is None:
                return job
            if current.status not in {"queued", "running"}:
                return current
            with _ACTIVE_LOCK:
                thread = _ACTIVE_THREADS.get(current.robustness_id)
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

            stale_after = int(
                os.environ.get(
                    "RESEARCH_ROBUSTNESS_JOB_STALE_SECONDS",
                    os.environ.get("RESEARCH_JOB_STALE_SECONDS", "900"),
                )
            )
            stale_queued_after = int(
                os.environ.get(
                    "RESEARCH_ROBUSTNESS_JOB_QUEUED_STALE_SECONDS",
                    os.environ.get("RESEARCH_JOB_QUEUED_STALE_SECONDS", "60"),
                )
            )
            grace = int(os.environ.get("RESEARCH_JOB_RUNNING_GRACE_SECONDS", "5"))

            if current.status == "queued":
                if age < stale_queued_after:
                    return current
                reason = (
                    "Robustheitstest blieb in queued hängen "
                    "(Prozessneustart vor Worker-Start)."
                )
            else:
                if age < grace:
                    return current
                if age < stale_after and thread is not None:
                    return current
                reason = "Robustheitstest unterbrochen (Prozessneustart oder Worker verloren)."

            current.status = "failed"
            current.finished_at = _utc_now()
            current.updated_at = current.finished_at
            current.error = reason
            current.error_detail = (
                "V1 limitation: in-process robustness jobs do not resume after restart. "
                "Create a new robustness test (new config) instead."
            )
            self._atomic_write(self._job_path(current.robustness_id), current.to_dict())
            return current

    def register_thread(self, robustness_id: str, thread: threading.Thread) -> None:
        with _ACTIVE_LOCK:
            _ACTIVE_THREADS[robustness_id] = thread

    def clear_thread(self, robustness_id: str) -> None:
        with _ACTIVE_LOCK:
            _ACTIVE_THREADS.pop(robustness_id, None)

    def is_active(self, robustness_id: str) -> bool:
        with _ACTIVE_LOCK:
            thread = _ACTIVE_THREADS.get(robustness_id)
            return thread is not None and thread.is_alive()
