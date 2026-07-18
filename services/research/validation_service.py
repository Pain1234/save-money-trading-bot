"""Validation Study read/write surface for the Research API (Issue #249 / P4.7d).

Aggregates already-produced evidence — completed experiments/runs
(#141-#147, #242), robustness manifests (#247) and versioned gate
evaluation records (#248) — into one reviewable Validation Study. This
service runs **no** second backtest engine, re-evaluates **no** gate, and
performs **no** live/paper promotion: the only new persisted facts are the
study's pinned evidence snapshot plus an optional human-entered final
decision (see ``research.validation_study.StudyDecision``).

Create resolves **exact** complete ``run_id`` pins (rejecting failed /
invalidated / non-complete registry rows) and persists an immutable
:class:`~research.validation_study.StudyEvidenceSnapshot`. Read/get
hydrates from that snapshot — never from the current latest registry
entry for an ``experiment_id``. Decisions bind to ``snapshot_id`` and
require re-verification; decided studies fail closed when underlying
evidence no longer matches the snapshot.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from research.gate_evaluator import (
    GateEvaluationError,
    GateResultStore,
    GateRunRecord,
    verify_gate_record_artifact_checksums,
)
from research.gate_policy import GatePolicyError, verify_policy_content_hash
from research.gate_service import GateService
from research.registry import ExperimentRegistry, RegistryEntry
from research.robustness import robustness_manifest_path, verify_robustness_manifest_seal
from research.robustness_jobs import RobustnessJobStore
from research.robustness_service import RobustnessOrchestrationService
from research.run_manifest import load_run_manifest
from research.service import ResearchReadService, assert_safe_id
from research.validation_study import (
    VALIDATION_STUDY_SCHEMA_VERSION,
    PinnedGateEvidence,
    PinnedRobustnessEvidence,
    PinnedRunEvidence,
    StudyDecision,
    StudyEvidenceSnapshot,
    StudyRecord,
    StudyStore,
    checksums_digest,
    compute_study_id,
    content_digest,
)
from research.write_service import ResearchWriteError, repo_root_from_env


def _utc_now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _clean_id_list(raw: Any, *, field: str) -> list[str]:
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise ResearchWriteError(
            f"{field} muss eine Liste sein", field_errors={field: "muss Liste sein"}
        )
    out: list[str] = []
    for item in raw:
        try:
            out.append(assert_safe_id(str(item), field=field))
        except ValueError as exc:
            raise ResearchWriteError(str(exc), field_errors={field: str(exc)}) from exc
    return out


def gate_evidence_content_hash(record: GateRunRecord) -> str:
    """Hash of sealed gate evidence fields (excludes mutable invalidation status)."""
    return content_digest(
        {
            "gate_run_id": record.gate_run_id,
            "policy_version": record.policy_version,
            "policy_content_hash": record.policy_content_hash,
            "run_code_commit": record.run_code_commit,
            "evaluation_code_commit": record.evaluation_code_commit,
            "experiment_id": record.experiment_id,
            "run_id": record.run_id,
            "robustness_run_ids": list(record.robustness_run_ids),
            "dataset_id": record.dataset_id,
            "dataset_content_hash": record.dataset_content_hash,
            "artifact_checksums": dict(sorted(record.artifact_checksums.items())),
            "measurements": dict(sorted(record.measurements.items())),
            "gates": [g.to_dict() for g in record.gates],
            "overall_status": record.overall_status,
        }
    )


class ValidationStudyService:
    def __init__(self, root: Path, *, repo_root: Path | None = None) -> None:
        self.root = root.resolve()
        self.repo_root = (repo_root or repo_root_from_env()).resolve()
        self.store = StudyStore(self.root)
        self.registry = ExperimentRegistry(self.root)
        self.robustness_jobs = RobustnessJobStore(self.root)
        self.gates = GateResultStore(self.root)
        self.read_service = ResearchReadService(self.root)
        self.robustness_service = RobustnessOrchestrationService(
            self.root, repo_root=self.repo_root
        )
        self.gate_service = GateService(self.root, repo_root=self.repo_root)

    # --- reference resolution (fail closed; never invent evidence) --------

    def _latest_status_by_run(self, experiment_id: str) -> dict[str, RegistryEntry]:
        latest: dict[str, RegistryEntry] = {}
        for entry in self.registry.list_entries():
            if entry.experiment_id == experiment_id:
                latest[entry.run_id] = entry
        return latest

    def _resolve_complete_entry(self, experiment_id: str, *, field: str) -> RegistryEntry:
        """Pin the newest *complete* run for ``experiment_id`` (never failed/invalidated)."""
        by_run = self._latest_status_by_run(experiment_id)
        if not by_run:
            raise ResearchWriteError(
                f"Experiment {experiment_id!r} ist nicht in der Registry bekannt "
                "(nur abgeschlossene Läufe können referenziert werden)",
                field_errors={field: "unbekannt"},
            )
        complete = [e for e in by_run.values() if e.status == "complete"]
        if not complete:
            statuses = sorted({e.status for e in by_run.values()})
            raise ResearchWriteError(
                f"Experiment {experiment_id!r} hat keinen complete-Lauf "
                f"(aktueller Status: {', '.join(statuses)})",
                field_errors={field: f"status={statuses[0]}"},
            )
        return max(complete, key=lambda e: e.created_at)

    def _pin_run_evidence(self, entry: RegistryEntry, *, field: str) -> PinnedRunEvidence:
        if entry.status != "complete":
            raise ResearchWriteError(
                f"run_id {entry.run_id!r} ist nicht complete (status={entry.status})",
                field_errors={field: f"status={entry.status}"},
            )
        try:
            # Re-verify artifacts against the trusted registry checksum map.
            verified = self.registry.show(entry.run_id, verify=True)
        except (KeyError, FileNotFoundError, ValueError, OSError) as exc:
            raise ResearchWriteError(
                f"run_id {entry.run_id!r} Artefakte nicht verifizierbar: {exc}",
                field_errors={field: "checksum verify failed"},
            ) from exc
        if verified.status != "complete":
            raise ResearchWriteError(
                f"run_id {entry.run_id!r} ist nicht complete (status={verified.status})",
                field_errors={field: f"status={verified.status}"},
            )
        try:
            manifest = load_run_manifest(Path(verified.artifact_path) / "run_manifest.json")
        except (OSError, ValueError) as exc:
            raise ResearchWriteError(
                f"run_id {entry.run_id!r}: RunManifest fehlt oder ungültig",
                field_errors={field: "missing run_manifest"},
            ) from exc
        return PinnedRunEvidence(
            experiment_id=verified.experiment_id,
            run_id=verified.run_id,
            checksums_digest=checksums_digest(verified.checksums),
            dataset_id=manifest.dataset_id,
            dataset_content_hash=manifest.dataset_content_hash,
            git_commit=manifest.git_commit,
        )

    def _pin_robustness(
        self, robustness_id: str, *, pinned_run_ids: set[str]
    ) -> PinnedRobustnessEvidence:
        job = self.robustness_jobs.get(robustness_id)
        if job is None:
            raise ResearchWriteError(
                f"Robustheitstest {robustness_id!r} ist unbekannt",
                field_errors={"robustness_ids": f"unbekannt: {robustness_id}"},
            )
        if job.status != "completed":
            raise ResearchWriteError(
                f"Robustheitstest {robustness_id!r} ist nicht completed "
                f"(status={job.status})",
                field_errors={"robustness_ids": f"status={job.status}"},
            )
        if job.base_run_id not in pinned_run_ids:
            raise ResearchWriteError(
                f"Robustheitstest {robustness_id!r} gehört zu run_id "
                f"{job.base_run_id!r}, der nicht in dieser Study gepinnt ist",
                field_errors={
                    "robustness_ids": (
                        f"base_run_id {job.base_run_id} not in study pinned runs"
                    )
                },
            )
        try:
            manifest_hash = verify_robustness_manifest_seal(
                self.root,
                robustness_id,
                expected_hash=job.manifest_content_hash,
            )
        except (FileNotFoundError, ValueError, OSError) as exc:
            raise ResearchWriteError(
                f"Robustheitstest {robustness_id!r}: Manifest-Siegel ungültig "
                f"({exc})",
                field_errors={
                    "robustness_ids": f"manifest seal failed: {robustness_id}"
                },
            ) from exc
        return PinnedRobustnessEvidence(
            robustness_id=robustness_id, manifest_hash=manifest_hash
        )

    def _pin_gate(
        self, gate_run_id: str, *, pinned_run_ids: set[str]
    ) -> PinnedGateEvidence:
        record = self.gates.get(gate_run_id)
        if record is None:
            raise ResearchWriteError(
                f"Gate-Ergebnis {gate_run_id!r} ist unbekannt",
                field_errors={"gate_run_ids": f"unbekannt: {gate_run_id}"},
            )
        if record.status != "active":
            raise ResearchWriteError(
                f"Gate-Ergebnis {gate_run_id!r} ist nicht active "
                f"(status={record.status})",
                field_errors={"gate_run_ids": f"status={record.status}"},
            )
        if record.run_id not in pinned_run_ids:
            raise ResearchWriteError(
                f"Gate-Ergebnis {gate_run_id!r} gehört zu run_id "
                f"{record.run_id!r}, der nicht in dieser Study gepinnt ist",
                field_errors={
                    "gate_run_ids": (
                        f"run_id {record.run_id} not in study pinned runs"
                    )
                },
            )
        try:
            verify_policy_content_hash(record.policy_version, record.policy_content_hash)
        except GatePolicyError as exc:
            raise ResearchWriteError(
                str(exc),
                field_errors={
                    "gate_run_ids": "policy_content_hash mismatch — gate untrusted"
                },
            ) from exc
        try:
            verify_gate_record_artifact_checksums(self.root, record)
        except GateEvaluationError as exc:
            raise ResearchWriteError(
                str(exc),
                field_errors={
                    "gate_run_ids": (
                        "artifact_checksums mismatch — gate evidence untrusted"
                    ),
                    **exc.field_errors,
                },
            ) from exc
        return PinnedGateEvidence(
            gate_run_id=gate_run_id,
            content_hash=gate_evidence_content_hash(record),
        )

    def _build_snapshot(
        self,
        *,
        primary: PinnedRunEvidence,
        additional: list[PinnedRunEvidence],
        robustness: list[PinnedRobustnessEvidence],
        gates: list[PinnedGateEvidence],
    ) -> StudyEvidenceSnapshot:
        additional_t = tuple(additional)
        robustness_t = tuple(robustness)
        gates_t = tuple(gates)
        snapshot_id = StudyEvidenceSnapshot.compute_snapshot_id(
            primary=primary,
            additional=additional_t,
            robustness=robustness_t,
            gates=gates_t,
        )
        return StudyEvidenceSnapshot(
            snapshot_id=snapshot_id,
            primary=primary,
            additional=additional_t,
            robustness=robustness_t,
            gates=gates_t,
        )

    # --- create --------------------------------------------------------

    def create(self, payload: dict[str, Any]) -> dict[str, Any]:
        experiment_id_raw = str(payload.get("experiment_id") or "").strip()
        if not experiment_id_raw:
            raise ResearchWriteError(
                "experiment_id ist erforderlich",
                field_errors={"experiment_id": "erforderlich"},
            )
        try:
            experiment_id = assert_safe_id(experiment_id_raw, field="experiment_id")
        except ValueError as exc:
            raise ResearchWriteError(
                str(exc), field_errors={"experiment_id": str(exc)}
            ) from exc

        primary_entry = self._resolve_complete_entry(
            experiment_id, field="experiment_id"
        )
        primary_pin = self._pin_run_evidence(primary_entry, field="experiment_id")

        additional_experiment_ids = _clean_id_list(
            payload.get("additional_experiment_ids"), field="additional_experiment_ids"
        )
        additional_pins: list[PinnedRunEvidence] = []
        for exp_id in additional_experiment_ids:
            entry = self._resolve_complete_entry(
                exp_id, field="additional_experiment_ids"
            )
            additional_pins.append(
                self._pin_run_evidence(entry, field="additional_experiment_ids")
            )
        additional_run_ids = [p.run_id for p in additional_pins]
        pinned_run_ids = {primary_pin.run_id, *additional_run_ids}

        robustness_ids = _clean_id_list(payload.get("robustness_ids"), field="robustness_ids")
        robustness_pins = [
            self._pin_robustness(rid, pinned_run_ids=pinned_run_ids)
            for rid in robustness_ids
        ]

        gate_run_ids = _clean_id_list(payload.get("gate_run_ids"), field="gate_run_ids")
        gate_pins = [
            self._pin_gate(gid, pinned_run_ids=pinned_run_ids) for gid in gate_run_ids
        ]

        snapshot = self._build_snapshot(
            primary=primary_pin,
            additional=additional_pins,
            robustness=robustness_pins,
            gates=gate_pins,
        )

        strategy_version = primary_entry.strategy_version or None
        strategy_id: str | None = None
        try:
            summary = self.read_service._enrich(primary_entry)  # noqa: SLF001
            strategy_id = summary.strategy_id
        except (KeyError, PermissionError, OSError, ValueError):
            pass

        name = str(payload.get("name") or "").strip() or experiment_id
        notes = str(payload.get("notes") or "")

        study_id = compute_study_id(
            experiment_id=experiment_id,
            run_id=primary_pin.run_id,
            additional_experiment_ids=additional_experiment_ids,
            additional_run_ids=additional_run_ids,
            robustness_ids=robustness_ids,
            gate_run_ids=gate_run_ids,
            evidence_snapshot_id=snapshot.snapshot_id,
        )

        existing = self.store.get(study_id)
        if existing is not None:
            return {
                "study_id": study_id,
                "already_exists": True,
                "study": self._hydrate(existing),
            }

        record = StudyRecord(
            schema_version=VALIDATION_STUDY_SCHEMA_VERSION,
            study_id=study_id,
            created_at=_utc_now(),
            name=name,
            strategy_id=strategy_id,
            strategy_version=strategy_version,
            experiment_id=experiment_id,
            run_id=primary_pin.run_id,
            additional_experiment_ids=tuple(additional_experiment_ids),
            additional_run_ids=tuple(additional_run_ids),
            robustness_ids=tuple(robustness_ids),
            gate_run_ids=tuple(gate_run_ids),
            evidence_snapshot=snapshot,
            notes=notes,
            status="open",
            decision=None,
        )
        self.store.append(record)
        return {
            "study_id": study_id,
            "already_exists": False,
            "study": self._hydrate(record),
        }

    # --- snapshot verification -----------------------------------------

    def _verify_run_pin(self, pin: PinnedRunEvidence, *, field: str) -> RegistryEntry:
        try:
            entry = self.registry.show(pin.run_id, verify=True)
        except (KeyError, FileNotFoundError, ValueError, OSError) as exc:
            raise ResearchWriteError(
                f"pinned run {pin.run_id!r} nicht mehr verifizierbar: {exc}",
                field_errors={field: "snapshot verify failed"},
            ) from exc
        if entry.experiment_id != pin.experiment_id:
            raise ResearchWriteError(
                f"pinned run {pin.run_id!r} experiment_id drift",
                field_errors={field: "experiment_id mismatch"},
            )
        if entry.status != "complete":
            raise ResearchWriteError(
                f"pinned run {pin.run_id!r} is no longer complete "
                f"(status={entry.status})",
                field_errors={field: f"status={entry.status}"},
            )
        digest = checksums_digest(entry.checksums)
        if digest != pin.checksums_digest:
            raise ResearchWriteError(
                f"pinned run {pin.run_id!r} checksum digest mismatch",
                field_errors={field: "checksums_digest mismatch"},
            )
        try:
            manifest = load_run_manifest(Path(entry.artifact_path) / "run_manifest.json")
        except (OSError, ValueError) as exc:
            raise ResearchWriteError(
                f"pinned run {pin.run_id!r}: RunManifest fehlt",
                field_errors={field: "missing run_manifest"},
            ) from exc
        if (
            manifest.dataset_id != pin.dataset_id
            or manifest.dataset_content_hash != pin.dataset_content_hash
            or manifest.git_commit != pin.git_commit
        ):
            raise ResearchWriteError(
                f"pinned run {pin.run_id!r} dataset/git identity mismatch",
                field_errors={field: "identity mismatch"},
            )
        return entry

    def _verify_robustness_pin(self, pin: PinnedRobustnessEvidence) -> None:
        path = robustness_manifest_path(self.root, pin.robustness_id)
        if not path.is_file():
            raise ResearchWriteError(
                f"pinned robustness {pin.robustness_id!r}: Manifest fehlt",
                field_errors={"robustness_ids": "manifest missing"},
            )
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
        if actual != pin.manifest_hash:
            raise ResearchWriteError(
                f"pinned robustness {pin.robustness_id!r} manifest hash mismatch",
                field_errors={"robustness_ids": "manifest_hash mismatch"},
            )
        job = self.robustness_jobs.get(pin.robustness_id)
        if job is not None and job.status != "completed":
            raise ResearchWriteError(
                f"pinned robustness {pin.robustness_id!r} status={job.status}",
                field_errors={"robustness_ids": f"status={job.status}"},
            )

    def _verify_gate_pin(self, pin: PinnedGateEvidence) -> GateRunRecord:
        record = self.gates.get(pin.gate_run_id)
        if record is None:
            raise ResearchWriteError(
                f"pinned gate {pin.gate_run_id!r} fehlt",
                field_errors={"gate_run_ids": "missing"},
            )
        if record.status != "active":
            raise ResearchWriteError(
                f"pinned gate {pin.gate_run_id!r} is not active "
                f"(status={record.status})",
                field_errors={"gate_run_ids": f"status={record.status}"},
            )
        actual = gate_evidence_content_hash(record)
        if actual != pin.content_hash:
            raise ResearchWriteError(
                f"pinned gate {pin.gate_run_id!r} content hash mismatch",
                field_errors={"gate_run_ids": "content_hash mismatch"},
            )
        try:
            verify_policy_content_hash(record.policy_version, record.policy_content_hash)
        except GatePolicyError as exc:
            raise ResearchWriteError(
                str(exc),
                field_errors={"gate_run_ids": "policy_content_hash mismatch"},
            ) from exc
        try:
            verify_gate_record_artifact_checksums(self.root, record)
        except GateEvaluationError as exc:
            raise ResearchWriteError(
                str(exc),
                field_errors={
                    "gate_run_ids": (
                        "artifact_checksums mismatch — gate evidence untrusted"
                    ),
                    **exc.field_errors,
                },
            ) from exc
        return record

    def verify_snapshot(self, snapshot: StudyEvidenceSnapshot) -> None:
        """Re-verify every pin in ``snapshot``; raise ``ResearchWriteError`` on drift."""
        self._verify_run_pin(snapshot.primary, field="experiment_id")
        for pin in snapshot.additional:
            self._verify_run_pin(pin, field="additional_experiment_ids")
        for pin in snapshot.robustness:
            self._verify_robustness_pin(pin)
        for pin in snapshot.gates:
            self._verify_gate_pin(pin)

    # --- resolution helpers (snapshot-pinned, no second engine) ----------

    def _resolve_pinned_run_summary(self, pin: PinnedRunEvidence) -> dict[str, Any]:
        try:
            entry = self.registry.show(pin.run_id, verify=False)
            summary = self.read_service._enrich(entry)  # noqa: SLF001
            return dict(summary.__dict__)
        except (KeyError, PermissionError, OSError, ValueError):
            return {
                "experiment_id": pin.experiment_id,
                "run_id": pin.run_id,
                "status": "unknown",
            }

    def _resolve_robustness(self, robustness_id: str) -> dict[str, Any]:
        try:
            status = self.robustness_service.get_status(robustness_id)
        except (KeyError, ValueError):
            return {"robustness_id": robustness_id, "status": "unknown", "manifest": None}
        manifest = self.robustness_service.get_manifest(robustness_id)
        return {**status, "manifest": manifest}

    def _resolve_gate(self, gate_run_id: str) -> dict[str, Any] | None:
        try:
            return self.gate_service.get(gate_run_id)
        except (KeyError, ValueError, ResearchWriteError):
            return None

    @staticmethod
    def _progress(
        *,
        experiment_summaries: list[dict[str, Any]],
        robustness_details: list[dict[str, Any]],
        gate_records: list[dict[str, Any]],
    ) -> dict[str, Any]:
        exp_complete = sum(1 for s in experiment_summaries if s.get("status") == "complete")
        rob_complete = sum(1 for r in robustness_details if r.get("status") == "completed")
        rob_failed = sum(1 for r in robustness_details if r.get("status") == "failed")
        rob_running = sum(
            1 for r in robustness_details if r.get("status") in {"created", "queued", "running"}
        )
        gate_pass = sum(1 for g in gate_records if g.get("overall_status") == "pass")
        gate_fail = sum(1 for g in gate_records if g.get("overall_status") == "fail")
        return {
            "experiments": {
                "total": len(experiment_summaries),
                "complete": exp_complete,
            },
            "robustness": {
                "total": len(robustness_details),
                "completed": rob_complete,
                "failed": rob_failed,
                "running": rob_running,
            },
            "gates": {
                "total": len(gate_records),
                "pass": gate_pass,
                "fail": gate_fail,
            },
        }

    @staticmethod
    def _reproducibility_from_snapshot(
        snapshot: StudyEvidenceSnapshot, gate_records: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """Reproducibility from the *pinned* snapshot, preferring bound gate fields."""
        anchor: dict[str, Any] | None = None
        for record in sorted(
            gate_records, key=lambda g: str(g.get("evaluated_at") or ""), reverse=True
        ):
            anchor = record
            break
        primary = snapshot.primary
        if anchor is not None:
            return {
                "git_commit": anchor.get("run_code_commit") or primary.git_commit,
                "evaluation_code_commit": anchor.get("evaluation_code_commit"),
                "dataset_id": anchor.get("dataset_id") or primary.dataset_id,
                "dataset_content_hash": (
                    anchor.get("dataset_content_hash") or primary.dataset_content_hash
                ),
                "policy_version": anchor.get("policy_version"),
                "policy_content_hash": anchor.get("policy_content_hash"),
                "source": "gate_run",
                "evidence_snapshot_id": snapshot.snapshot_id,
            }
        return {
            "git_commit": primary.git_commit,
            "evaluation_code_commit": None,
            "dataset_id": primary.dataset_id,
            "dataset_content_hash": primary.dataset_content_hash,
            "policy_version": None,
            "policy_content_hash": None,
            "source": "evidence_snapshot",
            "evidence_snapshot_id": snapshot.snapshot_id,
        }

    def _hydrate(
        self, record: StudyRecord, *, require_integrity: bool | None = None
    ) -> dict[str, Any]:
        """Hydrate display fields from the persisted snapshot (not latest registry).

        ``require_integrity`` defaults to True for decided studies (fail-closed)
        and False for open studies (surface ``evidence_integrity`` instead).
        """
        if require_integrity is None:
            require_integrity = record.status == "decided"

        integrity_ok = True
        integrity_error: str | None = None
        try:
            self.verify_snapshot(record.evidence_snapshot)
        except ResearchWriteError as exc:
            integrity_ok = False
            integrity_error = str(exc)
            if require_integrity:
                raise

        snapshot = record.evidence_snapshot
        pins = (snapshot.primary, *snapshot.additional)
        experiments = [self._resolve_pinned_run_summary(p) for p in pins]
        robustness_details = [
            self._resolve_robustness(r.robustness_id) for r in snapshot.robustness
        ]
        gate_records = [
            g
            for g in (self._resolve_gate(p.gate_run_id) for p in snapshot.gates)
            if g
        ]

        robustness_by_type: dict[str, list[dict[str, Any]]] = {}
        for detail in robustness_details:
            test_type = str(detail.get("test_type") or "unknown")
            robustness_by_type.setdefault(test_type, []).append(detail)

        return {
            **record.to_dict(),
            "experiments": experiments,
            "robustness": robustness_details,
            "robustness_by_type": robustness_by_type,
            "gates": gate_records,
            "progress": self._progress(
                experiment_summaries=experiments,
                robustness_details=robustness_details,
                gate_records=gate_records,
            ),
            "reproducibility": self._reproducibility_from_snapshot(snapshot, gate_records),
            "evidence_integrity": {
                "ok": integrity_ok,
                "error": integrity_error,
                "snapshot_id": snapshot.snapshot_id,
            },
        }

    # --- read ------------------------------------------------------------

    def get(self, study_id: str) -> dict[str, Any]:
        study_id = assert_safe_id(study_id, field="study_id")
        record = self.store.get(study_id)
        if record is None:
            raise KeyError(study_id)
        return self._hydrate(record)

    def list_all(
        self, *, experiment_id: str | None = None, status: str | None = None
    ) -> list[dict[str, Any]]:
        records = self.store.list_latest()
        if experiment_id:
            records = [
                r
                for r in records
                if r.experiment_id == experiment_id
                or experiment_id in r.additional_experiment_ids
            ]
        if status:
            records = [r for r in records if r.status == status]
        records.sort(key=lambda r: r.created_at, reverse=True)
        # List never fail-closes on a single broken decided study — mark integrity.
        return [self._hydrate(r, require_integrity=False) for r in records]

    # --- decision (human-owned; never automatic; never a promotion) ------

    def decide(self, study_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        study_id = assert_safe_id(study_id, field="study_id")
        outcome = str(payload.get("outcome") or "").strip()
        if outcome not in {"accept", "reject", "inconclusive"}:
            raise ResearchWriteError(
                "outcome muss 'accept', 'reject' oder 'inconclusive' sein",
                field_errors={"outcome": "ungültig"},
            )
        rationale = str(payload.get("rationale") or "").strip()
        if not rationale:
            raise ResearchWriteError(
                "rationale ist erforderlich", field_errors={"rationale": "erforderlich"}
            )
        decided_by = str(payload.get("decided_by") or "dashboard").strip() or "dashboard"

        record = self.store.get(study_id)
        if record is None:
            raise KeyError(study_id)

        # Fail-closed: refuse to decide if the immutable snapshot cannot be
        # re-verified against current trusted stores.
        self.verify_snapshot(record.evidence_snapshot)

        decision = StudyDecision(
            outcome=outcome,  # type: ignore[arg-type]
            rationale=rationale,
            decided_by=decided_by,
            decided_at=_utc_now(),
            evidence_snapshot_id=record.evidence_snapshot.snapshot_id,
        )
        try:
            updated = self.store.record_decision(study_id, decision, actor=decided_by)
        except KeyError as exc:
            raise KeyError(study_id) from exc
        except ValueError as exc:
            raise ResearchWriteError(str(exc), field_errors={"study_id": str(exc)}) from exc
        return self._hydrate(updated)
