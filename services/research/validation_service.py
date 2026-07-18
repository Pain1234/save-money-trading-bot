"""Validation Study read/write surface for the Research API (Issue #249 / P4.7d).

Aggregates already-produced evidence — completed experiments/runs
(#141-#147, #242), robustness manifests (#247) and versioned gate
evaluation records (#248) — into one reviewable Validation Study. This
service runs **no** second backtest engine, re-evaluates **no** gate, and
performs **no** live/paper promotion: the only new persisted fact is the
study's reference set plus an optional human-entered final decision (see
``research.validation_study.StudyDecision``). All display fields are
resolved live from the existing registry / robustness / gate stores so a
Study can never drift from — or duplicate — the evidence it references.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from research.gate_evaluator import GateResultStore
from research.gate_service import GateService
from research.registry import ExperimentRegistry
from research.robustness_jobs import RobustnessJobStore
from research.robustness_service import RobustnessOrchestrationService
from research.service import ResearchReadService, assert_safe_id
from research.validation_study import (
    VALIDATION_STUDY_SCHEMA_VERSION,
    StudyDecision,
    StudyRecord,
    StudyStore,
    compute_study_id,
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

    # --- reference validation (fail closed; never invent evidence) ---------

    def _require_experiment(self, experiment_id: str, *, field: str) -> None:
        matches = [e for e in self.registry.list_entries() if e.experiment_id == experiment_id]
        if not matches:
            raise ResearchWriteError(
                f"Experiment {experiment_id!r} ist nicht in der Registry bekannt "
                "(nur abgeschlossene Läufe können referenziert werden)",
                field_errors={field: "unbekannt"},
            )

    def _require_robustness(self, robustness_id: str) -> None:
        if self.robustness_jobs.get(robustness_id) is None:
            raise ResearchWriteError(
                f"Robustheitstest {robustness_id!r} ist unbekannt",
                field_errors={"robustness_ids": f"unbekannt: {robustness_id}"},
            )

    def _require_gate(self, gate_run_id: str) -> None:
        if self.gates.get(gate_run_id) is None:
            raise ResearchWriteError(
                f"Gate-Ergebnis {gate_run_id!r} ist unbekannt",
                field_errors={"gate_run_ids": f"unbekannt: {gate_run_id}"},
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
        self._require_experiment(experiment_id, field="experiment_id")

        # Authoritative run_id/strategy metadata come from the registry —
        # never trust client-supplied strategy fields (spoofing-safe).
        latest_entry = next(
            (
                e
                for e in reversed(self.registry.list_entries())
                if e.experiment_id == experiment_id
            ),
            None,
        )
        assert latest_entry is not None
        run_id = latest_entry.run_id
        strategy_version = latest_entry.strategy_version or None

        strategy_id: str | None = None
        try:
            detail = self.read_service.experiment_detail(experiment_id)
            strategy_id = detail["summary"].get("strategy_id")
        except (KeyError, PermissionError):
            pass

        additional_experiment_ids = _clean_id_list(
            payload.get("additional_experiment_ids"), field="additional_experiment_ids"
        )
        for exp_id in additional_experiment_ids:
            self._require_experiment(exp_id, field="additional_experiment_ids")

        robustness_ids = _clean_id_list(payload.get("robustness_ids"), field="robustness_ids")
        for rid in robustness_ids:
            self._require_robustness(rid)

        gate_run_ids = _clean_id_list(payload.get("gate_run_ids"), field="gate_run_ids")
        for gid in gate_run_ids:
            self._require_gate(gid)

        name = str(payload.get("name") or "").strip() or experiment_id
        notes = str(payload.get("notes") or "")

        study_id = compute_study_id(
            experiment_id=experiment_id,
            run_id=run_id,
            additional_experiment_ids=additional_experiment_ids,
            robustness_ids=robustness_ids,
            gate_run_ids=gate_run_ids,
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
            run_id=run_id,
            additional_experiment_ids=tuple(additional_experiment_ids),
            robustness_ids=tuple(robustness_ids),
            gate_run_ids=tuple(gate_run_ids),
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

    # --- resolution helpers (read-only aggregation, no second engine) -----

    def _resolve_experiment_summary(self, experiment_id: str) -> dict[str, Any]:
        try:
            return dict(self.read_service.experiment_detail(experiment_id)["summary"])
        except (KeyError, PermissionError, ValueError):
            return {"experiment_id": experiment_id, "status": "unknown"}

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
        except (KeyError, ValueError):
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
    def _reproducibility(
        gate_records: list[dict[str, Any]], base_summary: dict[str, Any]
    ) -> dict[str, Any]:
        """Reproducibility fields, preferring the most recently evaluated bound gate.

        A gate record already carries the sealed evidence-binding contract
        (#248: run_code_commit, evaluation_code_commit, dataset_id,
        dataset_content_hash, policy_version + content hash) — reuse it
        rather than re-deriving from run artifacts (no second engine).
        """
        anchor: dict[str, Any] | None = None
        for record in sorted(
            gate_records, key=lambda g: str(g.get("evaluated_at") or ""), reverse=True
        ):
            anchor = record
            break
        if anchor is not None:
            return {
                "git_commit": anchor.get("run_code_commit"),
                "evaluation_code_commit": anchor.get("evaluation_code_commit"),
                "dataset_id": anchor.get("dataset_id"),
                "dataset_content_hash": anchor.get("dataset_content_hash"),
                "policy_version": anchor.get("policy_version"),
                "policy_content_hash": anchor.get("policy_content_hash"),
                "source": "gate_run",
            }
        return {
            "git_commit": base_summary.get("git_commit"),
            "evaluation_code_commit": None,
            "dataset_id": base_summary.get("dataset_version"),
            "dataset_content_hash": None,
            "policy_version": None,
            "policy_content_hash": None,
            "source": "experiment_run",
        }

    def _hydrate(self, record: StudyRecord) -> dict[str, Any]:
        experiment_ids = [record.experiment_id, *record.additional_experiment_ids]
        experiments = [self._resolve_experiment_summary(e) for e in experiment_ids]
        robustness_details = [self._resolve_robustness(r) for r in record.robustness_ids]
        gate_records = [g for g in (self._resolve_gate(g) for g in record.gate_run_ids) if g]

        robustness_by_type: dict[str, list[dict[str, Any]]] = {}
        for detail in robustness_details:
            test_type = str(detail.get("test_type") or "unknown")
            robustness_by_type.setdefault(test_type, []).append(detail)

        base_summary = experiments[0] if experiments else {}

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
            "reproducibility": self._reproducibility(gate_records, base_summary),
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
        return [self._hydrate(r) for r in records]

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

        decision = StudyDecision(
            outcome=outcome,  # type: ignore[arg-type]
            rationale=rationale,
            decided_by=decided_by,
            decided_at=_utc_now(),
        )
        try:
            record = self.store.record_decision(study_id, decision, actor=decided_by)
        except KeyError as exc:
            raise KeyError(study_id) from exc
        except ValueError as exc:
            raise ResearchWriteError(str(exc), field_errors={"study_id": str(exc)}) from exc
        return self._hydrate(record)
