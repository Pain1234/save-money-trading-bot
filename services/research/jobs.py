"""Filesystem-backed research job status (Issue #242 / P4.6).

V1: jobs persist under ``artifacts/research/jobs/``. Execution uses an in-process
thread (no Celery/Redis). After a process restart, ``running`` jobs without a
live thread are marked failed on the next status read (documented V1 limit).
"""

from __future__ import annotations

import json
import os
import threading
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

JobStatus = Literal["created", "queued", "running", "completed", "failed"]

_ACTIVE_LOCK = threading.Lock()
_ACTIVE_THREADS: dict[str, threading.Thread] = {}

_STALE_RUNNING_SECONDS = int(os.environ.get("RESEARCH_JOB_STALE_SECONDS", "900"))


def _utc_now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


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
    """Append-friendly job file store (one JSON file per experiment_id)."""

    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self.jobs_dir = self.root / "artifacts" / "research" / "jobs"
        self.pending_dir = self.root / "artifacts" / "research" / "pending"

    def _job_path(self, experiment_id: str) -> Path:
        return self.jobs_dir / f"{experiment_id}.json"

    def pending_spec_path(self, experiment_id: str) -> Path:
        return self.pending_dir / experiment_id / "experiment.json"

    def save(self, job: ResearchJob) -> None:
        self.jobs_dir.mkdir(parents=True, exist_ok=True)
        path = self._job_path(job.experiment_id)
        path.write_text(
            json.dumps(job.to_dict(), sort_keys=True, indent=2) + "\n",
            encoding="utf-8",
        )

    def get(self, experiment_id: str) -> ResearchJob | None:
        path = self._job_path(experiment_id)
        if not path.is_file():
            return None
        raw = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            return None
        return ResearchJob.from_dict(raw)

    def list_jobs(self) -> list[ResearchJob]:
        if not self.jobs_dir.is_dir():
            return []
        jobs: list[ResearchJob] = []
        for path in sorted(self.jobs_dir.glob("*.json")):
            try:
                raw = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(raw, dict):
                    jobs.append(ResearchJob.from_dict(raw))
            except (OSError, json.JSONDecodeError, KeyError, TypeError):
                continue
        return jobs

    def mark_stale_if_needed(self, job: ResearchJob) -> ResearchJob:
        """Fail closed when a running job has no live worker after restart."""
        if job.status != "running":
            return job
        with _ACTIVE_LOCK:
            thread = _ACTIVE_THREADS.get(job.experiment_id)
            alive = thread is not None and thread.is_alive()
        if alive:
            return job
        started = job.started_at or job.updated_at
        try:
            started_dt = datetime.fromisoformat(started.replace("Z", "+00:00"))
        except ValueError:
            started_dt = datetime.now(UTC)
        age = (datetime.now(UTC) - started_dt.astimezone(UTC)).total_seconds()
        # Brief grace while the worker thread registers after status=running.
        if age < 5:
            return job
        if age < _STALE_RUNNING_SECONDS and thread is not None:
            return job
        job.status = "failed"
        job.finished_at = _utc_now()
        job.updated_at = job.finished_at
        job.error = "Research-Lauf unterbrochen (Prozessneustart oder Worker verloren)."
        job.error_detail = (
            "V1 limitation: in-process research jobs do not resume after restart. "
            "Re-create or start a new run from Strategy Lab / CLI."
        )
        self.save(job)
        return job
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
