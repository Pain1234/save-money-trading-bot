"""Validation Study record + append-only persistence (Issue #249 / P4.7d).

A Validation Study aggregates references to already-produced evidence —
completed experiments/runs (#141-#147, #242), robustness manifests (#247)
and versioned gate evaluation records (#248) — into one reviewable unit.
This module runs **no** second backtest engine, re-evaluates **no** gate,
and performs **no** live/paper promotion: it only binds IDs that already
exist elsewhere, plus an optional human-entered final decision.

The final decision (:class:`StudyDecision`) is a human-owned judgement,
never inferred automatically from a gate's ``overall_status`` and never a
promotion trigger. Persistence mirrors ``research.gate_evaluator.
GateResultStore`` (#248) and ``research.registry`` (#145): a record is never
mutated in place. Recording a decision appends a superseding record plus an
audit sidecar; a study can only be decided once (new evidence → a new
Study, not an edited one — see ``AGENTS.md`` §8, do not overwrite historical
research).

Public/private boundary (#181): this module stores only IDs, hashes and
human-entered text — never private Strategy V1 numbers. Public Core ships
generic framework code + synthetic fixtures only.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

VALIDATION_STUDY_SCHEMA_VERSION = "1.0"
StudyStatus = Literal["open", "decided"]
StudyDecisionOutcome = Literal["accept", "reject", "inconclusive"]


def _utc_now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


@dataclass(frozen=True)
class StudyDecision:
    """Human-owned final decision — never automatic, never a promotion trigger.

    ``outcome`` intentionally mirrors the generic P5 decision vocabulary
    (accept / reject / inconclusive, see ``docs/research/p5/P5_DECISION_RULES.md``)
    without binding this generic infrastructure to the private Strategy V1
    decision itself (#205 remains the canonical, human-signed-off decision).
    """

    outcome: StudyDecisionOutcome
    rationale: str
    decided_by: str
    decided_at: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "outcome": self.outcome,
            "rationale": self.rationale,
            "decided_by": self.decided_by,
            "decided_at": self.decided_at,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> StudyDecision:
        return cls(
            outcome=raw["outcome"],
            rationale=str(raw["rationale"]),
            decided_by=str(raw["decided_by"]),
            decided_at=str(raw["decided_at"]),
        )


@dataclass(frozen=True)
class StudyRecord:
    """One append-only Validation Study aggregate record."""

    schema_version: str
    study_id: str
    created_at: str
    name: str
    strategy_id: str | None
    strategy_version: str | None
    experiment_id: str
    run_id: str | None
    additional_experiment_ids: tuple[str, ...]
    robustness_ids: tuple[str, ...]
    gate_run_ids: tuple[str, ...]
    notes: str
    status: StudyStatus
    decision: StudyDecision | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "study_id": self.study_id,
            "created_at": self.created_at,
            "name": self.name,
            "strategy_id": self.strategy_id,
            "strategy_version": self.strategy_version,
            "experiment_id": self.experiment_id,
            "run_id": self.run_id,
            "additional_experiment_ids": list(self.additional_experiment_ids),
            "robustness_ids": list(self.robustness_ids),
            "gate_run_ids": list(self.gate_run_ids),
            "notes": self.notes,
            "status": self.status,
            "decision": self.decision.to_dict() if self.decision is not None else None,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> StudyRecord:
        decision_raw = raw.get("decision")
        return cls(
            schema_version=str(raw["schema_version"]),
            study_id=str(raw["study_id"]),
            created_at=str(raw["created_at"]),
            name=str(raw.get("name") or ""),
            strategy_id=raw.get("strategy_id"),
            strategy_version=raw.get("strategy_version"),
            experiment_id=str(raw["experiment_id"]),
            run_id=raw.get("run_id"),
            additional_experiment_ids=tuple(
                str(x) for x in raw.get("additional_experiment_ids", [])
            ),
            robustness_ids=tuple(str(x) for x in raw.get("robustness_ids", [])),
            gate_run_ids=tuple(str(x) for x in raw.get("gate_run_ids", [])),
            notes=str(raw.get("notes") or ""),
            status=raw.get("status", "open"),
            decision=StudyDecision.from_dict(decision_raw) if decision_raw else None,
        )


def compute_study_id(
    *,
    experiment_id: str,
    run_id: str | None,
    additional_experiment_ids: list[str],
    robustness_ids: list[str],
    gate_run_ids: list[str],
) -> str:
    """Deterministic study_id — idempotent create, mirrors experiment/robustness/gate ids."""
    payload = {
        "experiment_id": experiment_id,
        "run_id": run_id,
        "additional_experiment_ids": sorted(additional_experiment_ids),
        "robustness_ids": sorted(robustness_ids),
        "gate_run_ids": sorted(gate_run_ids),
    }
    text = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return f"study_{digest}"


class StudyStore:
    """Append-only JSONL Validation Study log, mirrors ``GateResultStore`` (#248)."""

    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self.path = self.root / "artifacts" / "research" / "validation" / "registry.jsonl"
        self.decisions_dir = self.root / "artifacts" / "research" / "validation" / "decisions"

    def _append_line(self, record: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, sort_keys=True) + "\n")

    def list_entries(self) -> list[StudyRecord]:
        if not self.path.exists():
            return []
        entries: list[StudyRecord] = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            entries.append(StudyRecord.from_dict(json.loads(line)))
        return entries

    def _latest_by_id(self) -> dict[str, StudyRecord]:
        latest: dict[str, StudyRecord] = {}
        for entry in self.list_entries():
            latest[entry.study_id] = entry
        return latest

    def get(self, study_id: str) -> StudyRecord | None:
        """Most recent record for ``study_id`` (reflects a recorded decision, if any)."""
        return self._latest_by_id().get(study_id)

    def list_latest(self) -> list[StudyRecord]:
        return list(self._latest_by_id().values())

    def append(self, record: StudyRecord) -> None:
        existing = self.get(record.study_id)
        if existing is not None:
            msg = f"duplicate study_id forbidden: {record.study_id}"
            raise ValueError(msg)
        self._append_line(record.to_dict())

    def record_decision(
        self, study_id: str, decision: StudyDecision, *, actor: str
    ) -> StudyRecord:
        """Append-only decision + superseding record (mirrors gate invalidate pattern)."""
        entry = self.get(study_id)
        if entry is None:
            raise KeyError(study_id)
        if entry.status == "decided":
            msg = f"validation study already decided: {study_id}"
            raise ValueError(msg)
        self.decisions_dir.mkdir(parents=True, exist_ok=True)
        sidecar = self.decisions_dir / f"{study_id}.jsonl"
        sidecar_record = {
            "study_id": study_id,
            "decision": decision.to_dict(),
            "provenance": {"actor": actor, "at": _utc_now()},
        }
        with sidecar.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(sidecar_record, sort_keys=True) + "\n")
        superseding = replace(entry, status="decided", decision=decision)
        self._append_line(superseding.to_dict())
        return superseding
