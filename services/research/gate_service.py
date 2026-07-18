"""Gate evaluation write/read surface for the Research API (Issue #248 / P4.7c).

Thin payload-validation wrapper around :class:`research.gate_evaluator.
GateEvaluator` / ``GateResultStore``, mirroring
``research.robustness_service.RobustnessOrchestrationService`` (#247) and
``research.write_service.ResearchWriteService`` (#242): same
``ResearchWriteError``-shaped field errors, same ``assert_safe_id`` guard on
path-derived identifiers. No live/paper promotion; evaluation is synchronous
and read-only over already-produced artifacts.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from research.gate_evaluator import (
    GateEvaluationError,
    GateEvaluator,
    GateResultStore,
    GateRunRecord,
    verify_gate_record_artifact_checksums,
)
from research.gate_policy import (
    GatePolicy,
    GatePolicyError,
    list_policy_versions,
    verify_policy_content_hash,
)
from research.gate_policy import get_policy as _get_policy
from research.service import assert_safe_id
from research.write_service import ResearchWriteError, repo_root_from_env


def _policy_to_public_dict(policy: GatePolicy) -> dict[str, Any]:
    from research.gate_policy import compute_policy_content_hash

    return {
        **policy.to_dict(),
        "content_hash": compute_policy_content_hash(policy),
    }


def _assert_record_policy_trusted(record: GateRunRecord) -> None:
    """Fail closed if persisted policy content no longer matches the version.

    Same-version silent edits must not be presented as trusted gate evidence
    via ``get`` / ``list_all``.
    """
    try:
        verify_policy_content_hash(record.policy_version, record.policy_content_hash)
    except GatePolicyError as exc:
        raise ResearchWriteError(
            str(exc),
            field_errors={
                "policy_content_hash": (
                    "mismatch — gate record untrusted under current policy"
                )
            },
        ) from exc


def _record_to_public_dict(
    root: Path, record: GateRunRecord, *, fail_closed_active: bool = True
) -> dict[str, Any]:
    """Serialize a gate record after policy + artifact integrity checks.

    Active records fail closed on evidence tampering (same posture as policy
    hash). Invalidated records may still be returned with
    ``evidence_integrity.ok=false`` so audit history remains readable.
    """
    _assert_record_policy_trusted(record)
    payload = record.to_dict()
    try:
        verify_gate_record_artifact_checksums(root, record)
    except GateEvaluationError as exc:
        if record.status == "active" and fail_closed_active:
            raise ResearchWriteError(
                str(exc),
                field_errors={
                    "artifact_checksums": (
                        "mismatch — gate record evidence untrusted"
                    ),
                    **exc.field_errors,
                },
            ) from exc
        payload["evidence_integrity"] = {"ok": False, "error": str(exc)}
        return payload
    payload["evidence_integrity"] = {"ok": True, "error": None}
    return payload


class GateService:
    def __init__(self, root: Path, *, repo_root: Path | None = None) -> None:
        self.root = root.resolve()
        self.repo_root = (repo_root or repo_root_from_env()).resolve()
        self.evaluator = GateEvaluator(self.root, repo_root=self.repo_root)
        self.store = GateResultStore(self.root)

    def evaluate(self, payload: dict[str, Any]) -> dict[str, Any]:
        run_id_raw = str(payload.get("run_id") or "").strip()
        if not run_id_raw:
            raise ResearchWriteError(
                "run_id ist erforderlich", field_errors={"run_id": "erforderlich"}
            )
        try:
            run_id = assert_safe_id(run_id_raw, field="run_id")
        except ValueError as exc:
            raise ResearchWriteError(
                str(exc), field_errors={"run_id": str(exc)}
            ) from exc

        policy_version = str(payload.get("policy_version") or "").strip()
        if not policy_version:
            raise ResearchWriteError(
                "policy_version ist erforderlich",
                field_errors={"policy_version": "erforderlich"},
            )

        robustness_run_ids_raw = payload.get("robustness_run_ids") or []
        if not isinstance(robustness_run_ids_raw, list):
            raise ResearchWriteError(
                "robustness_run_ids muss eine Liste sein",
                field_errors={"robustness_run_ids": "muss Liste sein"},
            )
        robustness_run_ids: list[str] = []
        for raw_id in robustness_run_ids_raw:
            try:
                robustness_run_ids.append(assert_safe_id(str(raw_id), field="robustness_run_ids"))
            except ValueError as exc:
                raise ResearchWriteError(
                    str(exc), field_errors={"robustness_run_ids": str(exc)}
                ) from exc

        try:
            record = self.evaluator.evaluate(
                run_id=run_id,
                policy_version=policy_version,
                robustness_run_ids=robustness_run_ids,
            )
        except GateEvaluationError as exc:
            raise ResearchWriteError(str(exc), field_errors=exc.field_errors) from exc
        return _record_to_public_dict(self.root, record)

    def get(self, gate_run_id: str) -> dict[str, Any]:
        gate_run_id = assert_safe_id(gate_run_id, field="gate_run_id")
        record = self.store.get(gate_run_id)
        if record is None:
            raise KeyError(gate_run_id)
        return _record_to_public_dict(self.root, record)

    def list_all(self, *, run_id: str | None = None) -> list[dict[str, Any]]:
        entries = self.store.list_entries()
        # Most-recent-per-id (append-only log may hold a superseding
        # invalidation record after the original active one).
        latest: dict[str, GateRunRecord] = {}
        for entry in entries:
            latest[entry.gate_run_id] = entry
        items: list[dict[str, Any]] = []
        for entry in latest.values():
            items.append(_record_to_public_dict(self.root, entry))
        if run_id:
            items = [i for i in items if i["run_id"] == run_id]
        items.sort(key=lambda i: i["evaluated_at"], reverse=True)
        return items

    def invalidate(self, gate_run_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        gate_run_id = assert_safe_id(gate_run_id, field="gate_run_id")
        reason = str(payload.get("reason") or "").strip()
        if not reason:
            raise ResearchWriteError(
                "reason ist erforderlich", field_errors={"reason": "erforderlich"}
            )
        actor = str(payload.get("actor") or "api").strip() or "api"
        try:
            self.store.invalidate(gate_run_id, reason=reason, actor=actor)
        except KeyError as exc:
            raise KeyError(gate_run_id) from exc
        except ValueError as exc:
            raise ResearchWriteError(
                str(exc), field_errors={"gate_run_id": str(exc)}
            ) from exc
        record = self.store.get(gate_run_id)
        assert record is not None
        # Invalidated: return with integrity flag rather than hard-failing.
        return _record_to_public_dict(self.root, record, fail_closed_active=False)

    def list_policies(self) -> list[dict[str, Any]]:
        return [_policy_to_public_dict(_get_policy(v)) for v in list_policy_versions()]
