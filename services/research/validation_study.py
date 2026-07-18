"""Validation Study record + append-only persistence (Issue #249 / P4.7d).

A Validation Study aggregates references to already-produced evidence —
completed experiments/runs (#141-#147, #242), robustness manifests (#247)
and versioned gate evaluation records (#248) — into one reviewable unit.
This module runs **no** second backtest engine, re-evaluates **no** gate,
and performs **no** live/paper promotion: it only binds IDs that already
exist elsewhere, plus an optional human-entered final decision.

Evidence is pinned at create time as an immutable
:class:`StudyEvidenceSnapshot` (exact ``run_id`` pins, artifact checksum
digests, dataset identity, robustness manifest hashes, gate content
hashes, git commit). Reads hydrate from that snapshot — never from the
*current* latest registry entry — so a decided study cannot drift when a
newer run completes for the same experiment.

The final decision (:class:`StudyDecision`) is a human-owned judgement,
never inferred automatically from a gate's ``overall_status`` and never a
promotion trigger. Persistence mirrors ``research.gate_evaluator.
GateResultStore`` (#248) and ``research.registry`` (#145): a record is never
mutated in place. Recording a decision appends a superseding record plus an
audit sidecar; a study can only be decided once (new evidence → a new
Study, not an edited one — see ``AGENTS.md`` §8, do not overwrite historical
research). Decisions bind to ``evidence_snapshot.snapshot_id`` and require
re-verification of the snapshot before they are accepted.

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

VALIDATION_STUDY_SCHEMA_VERSION = "1.1"
StudyStatus = Literal["open", "decided"]
StudyDecisionOutcome = Literal["accept", "reject", "inconclusive"]


def _utc_now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _canonical_json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def checksums_digest(checksums: dict[str, str]) -> str:
    """Stable digest of a trusted registry checksum map."""
    return hashlib.sha256(
        _canonical_json({str(k): str(v) for k, v in sorted(checksums.items())}).encode(
            "utf-8"
        )
    ).hexdigest()


def content_digest(payload: dict[str, Any]) -> str:
    """SHA-256 of a canonical JSON object (gate / snapshot hashing)."""
    return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class PinnedRunEvidence:
    """Exact experiment/run pin + trusted registry checksum digest."""

    experiment_id: str
    run_id: str
    checksums_digest: str
    dataset_id: str
    dataset_content_hash: str
    git_commit: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "experiment_id": self.experiment_id,
            "run_id": self.run_id,
            "checksums_digest": self.checksums_digest,
            "dataset_id": self.dataset_id,
            "dataset_content_hash": self.dataset_content_hash,
            "git_commit": self.git_commit,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> PinnedRunEvidence:
        return cls(
            experiment_id=str(raw["experiment_id"]),
            run_id=str(raw["run_id"]),
            checksums_digest=str(raw["checksums_digest"]),
            dataset_id=str(raw["dataset_id"]),
            dataset_content_hash=str(raw["dataset_content_hash"]),
            git_commit=str(raw["git_commit"]),
        )


@dataclass(frozen=True)
class PinnedRobustnessEvidence:
    robustness_id: str
    manifest_hash: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "robustness_id": self.robustness_id,
            "manifest_hash": self.manifest_hash,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> PinnedRobustnessEvidence:
        return cls(
            robustness_id=str(raw["robustness_id"]),
            manifest_hash=str(raw["manifest_hash"]),
        )


@dataclass(frozen=True)
class PinnedGateEvidence:
    gate_run_id: str
    content_hash: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "gate_run_id": self.gate_run_id,
            "content_hash": self.content_hash,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> PinnedGateEvidence:
        return cls(
            gate_run_id=str(raw["gate_run_id"]),
            content_hash=str(raw["content_hash"]),
        )


@dataclass(frozen=True)
class StudyEvidenceSnapshot:
    """Immutable evidence binding captured at study create time.

    Reads must hydrate from this snapshot (pinned ``run_id``s), not from
    whatever the registry currently lists as the latest entry for an
    ``experiment_id``.
    """

    snapshot_id: str
    primary: PinnedRunEvidence
    additional: tuple[PinnedRunEvidence, ...]
    robustness: tuple[PinnedRobustnessEvidence, ...]
    gates: tuple[PinnedGateEvidence, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "snapshot_id": self.snapshot_id,
            "primary": self.primary.to_dict(),
            "additional": [p.to_dict() for p in self.additional],
            "robustness": [r.to_dict() for r in self.robustness],
            "gates": [g.to_dict() for g in self.gates],
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> StudyEvidenceSnapshot:
        return cls(
            snapshot_id=str(raw["snapshot_id"]),
            primary=PinnedRunEvidence.from_dict(raw["primary"]),
            additional=tuple(
                PinnedRunEvidence.from_dict(p) for p in raw.get("additional", [])
            ),
            robustness=tuple(
                PinnedRobustnessEvidence.from_dict(r) for r in raw.get("robustness", [])
            ),
            gates=tuple(PinnedGateEvidence.from_dict(g) for g in raw.get("gates", [])),
        )

    @staticmethod
    def compute_snapshot_id(
        *,
        primary: PinnedRunEvidence,
        additional: tuple[PinnedRunEvidence, ...],
        robustness: tuple[PinnedRobustnessEvidence, ...],
        gates: tuple[PinnedGateEvidence, ...],
    ) -> str:
        payload = {
            "primary": primary.to_dict(),
            "additional": [p.to_dict() for p in additional],
            "robustness": [r.to_dict() for r in robustness],
            "gates": [g.to_dict() for g in gates],
        }
        return f"evsnap_{content_digest(payload)}"


@dataclass(frozen=True)
class StudyDecision:
    """Human-owned final decision — never automatic, never a promotion trigger.

    ``outcome`` intentionally mirrors the generic P5 decision vocabulary
    (accept / reject / inconclusive, see ``docs/research/p5/P5_DECISION_RULES.md``)
    without binding this generic infrastructure to the private Strategy V1
    decision itself (#205 remains the canonical, human-signed-off decision).

    ``evidence_snapshot_id`` binds the decision to the immutable snapshot that
    was re-verified at decision time.
    """

    outcome: StudyDecisionOutcome
    rationale: str
    decided_by: str
    decided_at: str
    evidence_snapshot_id: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "outcome": self.outcome,
            "rationale": self.rationale,
            "decided_by": self.decided_by,
            "decided_at": self.decided_at,
            "evidence_snapshot_id": self.evidence_snapshot_id,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> StudyDecision:
        return cls(
            outcome=raw["outcome"],
            rationale=str(raw["rationale"]),
            decided_by=str(raw["decided_by"]),
            decided_at=str(raw["decided_at"]),
            evidence_snapshot_id=str(raw["evidence_snapshot_id"]),
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
    run_id: str
    additional_experiment_ids: tuple[str, ...]
    additional_run_ids: tuple[str, ...]
    robustness_ids: tuple[str, ...]
    gate_run_ids: tuple[str, ...]
    evidence_snapshot: StudyEvidenceSnapshot
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
            "additional_run_ids": list(self.additional_run_ids),
            "robustness_ids": list(self.robustness_ids),
            "gate_run_ids": list(self.gate_run_ids),
            "evidence_snapshot": self.evidence_snapshot.to_dict(),
            "notes": self.notes,
            "status": self.status,
            "decision": self.decision.to_dict() if self.decision is not None else None,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> StudyRecord:
        decision_raw = raw.get("decision")
        snapshot_raw = raw.get("evidence_snapshot")
        if not isinstance(snapshot_raw, dict):
            msg = "study record missing evidence_snapshot"
            raise ValueError(msg)
        additional_experiment_ids = tuple(
            str(x) for x in raw.get("additional_experiment_ids", [])
        )
        additional_run_ids = tuple(str(x) for x in raw.get("additional_run_ids", []))
        if len(additional_run_ids) != len(additional_experiment_ids):
            msg = "additional_run_ids must align with additional_experiment_ids"
            raise ValueError(msg)
        return cls(
            schema_version=str(raw["schema_version"]),
            study_id=str(raw["study_id"]),
            created_at=str(raw["created_at"]),
            name=str(raw.get("name") or ""),
            strategy_id=raw.get("strategy_id"),
            strategy_version=raw.get("strategy_version"),
            experiment_id=str(raw["experiment_id"]),
            run_id=str(raw["run_id"]),
            additional_experiment_ids=additional_experiment_ids,
            additional_run_ids=additional_run_ids,
            robustness_ids=tuple(str(x) for x in raw.get("robustness_ids", [])),
            gate_run_ids=tuple(str(x) for x in raw.get("gate_run_ids", [])),
            evidence_snapshot=StudyEvidenceSnapshot.from_dict(snapshot_raw),
            notes=str(raw.get("notes") or ""),
            status=raw.get("status", "open"),
            decision=StudyDecision.from_dict(decision_raw) if decision_raw else None,
        )


def compute_study_id(
    *,
    experiment_id: str,
    run_id: str,
    additional_experiment_ids: list[str],
    additional_run_ids: list[str],
    robustness_ids: list[str],
    gate_run_ids: list[str],
    evidence_snapshot_id: str,
) -> str:
    """Deterministic study_id — idempotent create on the same pinned evidence set."""
    if len(additional_experiment_ids) != len(additional_run_ids):
        msg = "additional_run_ids must align with additional_experiment_ids"
        raise ValueError(msg)
    additional = sorted(
        zip(additional_experiment_ids, additional_run_ids, strict=True),
        key=lambda pair: (pair[0], pair[1]),
    )
    payload = {
        "experiment_id": experiment_id,
        "run_id": run_id,
        "additional_experiments": [
            {"experiment_id": exp, "run_id": run} for exp, run in additional
        ],
        "robustness_ids": sorted(robustness_ids),
        "gate_run_ids": sorted(gate_run_ids),
        "evidence_snapshot_id": evidence_snapshot_id,
    }
    digest = content_digest(payload)
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
        if decision.evidence_snapshot_id != entry.evidence_snapshot.snapshot_id:
            msg = (
                "decision evidence_snapshot_id does not match study snapshot: "
                f"decision={decision.evidence_snapshot_id!r} "
                f"study={entry.evidence_snapshot.snapshot_id!r}"
            )
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
