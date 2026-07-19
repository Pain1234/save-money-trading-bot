"""Scorecard evaluation write/read surface for the Research API (#291)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from research.artifact_content import (
    ArtifactContentError,
    ArtifactContentResult,
    read_sealed_artifact_content,
)
from research.scorecard_detail import assemble_scorecard_detail
from research.scorecard_evaluator import (
    ScorecardEvaluationError,
    ScorecardEvaluator,
    ScorecardRecord,
    ScorecardResultStore,
    verify_scorecard_record_artifact_checksums,
)
from research.scorecard_policy import (
    ScorecardPolicy,
    ScorecardPolicyError,
    compute_scorecard_policy_content_hash,
    get_scorecard_policy,
    list_scorecard_policy_versions,
    verify_scorecard_policy_content_hash,
)
from research.service import assert_safe_id
from research.write_service import ResearchWriteError, repo_root_from_env


def _policy_to_public_dict(policy: ScorecardPolicy) -> dict[str, Any]:
    return {
        **policy.to_dict(),
        "content_hash": compute_scorecard_policy_content_hash(policy),
    }


def _assert_record_policy_trusted(record: ScorecardRecord) -> None:
    try:
        verify_scorecard_policy_content_hash(
            record.policy_version, record.policy_content_hash
        )
    except ScorecardPolicyError as exc:
        raise ResearchWriteError(
            str(exc),
            field_errors={
                "policy_content_hash": (
                    "mismatch — scorecard record untrusted under current policy"
                )
            },
        ) from exc


def _record_to_public_dict(
    root: Path, record: ScorecardRecord, *, fail_closed_active: bool = True
) -> dict[str, Any]:
    _assert_record_policy_trusted(record)
    payload = record.to_dict()
    try:
        verify_scorecard_record_artifact_checksums(root, record)
    except ScorecardEvaluationError as exc:
        if record.status == "active" and fail_closed_active:
            raise ResearchWriteError(
                str(exc),
                field_errors={
                    "artifact_checksums": (
                        "mismatch — scorecard record evidence untrusted"
                    ),
                    **exc.field_errors,
                },
            ) from exc
        payload["evidence_integrity"] = {"ok": False, "error": str(exc)}
        return payload
    payload["evidence_integrity"] = {"ok": True, "error": None}
    return payload


class ScorecardService:
    def __init__(self, root: Path, *, repo_root: Path | None = None) -> None:
        self.root = root.resolve()
        self.repo_root = (repo_root or repo_root_from_env()).resolve()
        self.evaluator = ScorecardEvaluator(self.root, repo_root=self.repo_root)
        self.store = ScorecardResultStore(self.root)

    def evaluate(self, payload: dict[str, Any]) -> dict[str, Any]:
        run_id_raw = str(payload.get("run_id") or "").strip()
        if not run_id_raw:
            raise ResearchWriteError(
                "run_id ist erforderlich", field_errors={"run_id": "erforderlich"}
            )
        try:
            run_id = assert_safe_id(run_id_raw, field="run_id")
        except ValueError as exc:
            raise ResearchWriteError(str(exc), field_errors={"run_id": str(exc)}) from exc

        policy_version = str(payload.get("policy_version") or "1.0").strip() or "1.0"

        gate_run_id_raw = payload.get("gate_run_id")
        gate_run_id: str | None = None
        if gate_run_id_raw is not None and str(gate_run_id_raw).strip():
            try:
                gate_run_id = assert_safe_id(str(gate_run_id_raw), field="gate_run_id")
            except ValueError as exc:
                raise ResearchWriteError(
                    str(exc), field_errors={"gate_run_id": str(exc)}
                ) from exc

        robustness_run_ids_raw = payload.get("robustness_run_ids") or []
        if not isinstance(robustness_run_ids_raw, list):
            raise ResearchWriteError(
                "robustness_run_ids muss eine Liste sein",
                field_errors={"robustness_run_ids": "muss Liste sein"},
            )
        robustness_run_ids: list[str] = []
        for raw_id in robustness_run_ids_raw:
            try:
                robustness_run_ids.append(
                    assert_safe_id(str(raw_id), field="robustness_run_ids")
                )
            except ValueError as exc:
                raise ResearchWriteError(
                    str(exc), field_errors={"robustness_run_ids": str(exc)}
                ) from exc

        try:
            record = self.evaluator.evaluate(
                run_id=run_id,
                policy_version=policy_version,
                gate_run_id=gate_run_id,
                robustness_run_ids=robustness_run_ids,
            )
        except ScorecardEvaluationError as exc:
            raise ResearchWriteError(str(exc), field_errors=exc.field_errors) from exc
        return _record_to_public_dict(self.root, record)

    def get(self, scorecard_id: str) -> dict[str, Any]:
        scorecard_id = assert_safe_id(scorecard_id, field="scorecard_id")
        record = self.store.get(scorecard_id)
        if record is None:
            raise KeyError(scorecard_id)
        return _record_to_public_dict(self.root, record)

    def get_detail(self, scorecard_id: str) -> dict[str, Any]:
        """Read-only regime-row + forensics join (#350). Summary GET stays unchanged."""
        scorecard_id = assert_safe_id(scorecard_id, field="scorecard_id")
        record = self.store.get(scorecard_id)
        if record is None:
            raise KeyError(scorecard_id)
        _assert_record_policy_trusted(record)
        try:
            detail = assemble_scorecard_detail(self.root, record)
        except ScorecardEvaluationError as exc:
            if record.status == "active":
                raise ResearchWriteError(
                    str(exc),
                    field_errors={
                        "artifact_checksums": (
                            "mismatch — scorecard detail evidence untrusted"
                        ),
                        **exc.field_errors,
                    },
                ) from exc
            # Invalidated: still assemble when possible, else surface integrity error.
            raise ResearchWriteError(
                str(exc),
                field_errors={
                    "artifact_checksums": "mismatch — invalidated scorecard unreadable",
                    **exc.field_errors,
                },
            ) from exc
        detail["evidence_integrity"] = {"ok": True, "error": None}
        return detail

    def get_artifact_content(
        self, scorecard_id: str, *, relative_path: str
    ) -> ArtifactContentResult:
        """Fail-closed read of one sealed run artifact pinned on the scorecard (#357)."""
        scorecard_id = assert_safe_id(scorecard_id, field="scorecard_id")
        record = self.store.get(scorecard_id)
        if record is None:
            raise ArtifactContentError(
                code="not_found", message="scorecard not found", status=404
            )
        try:
            return read_sealed_artifact_content(
                self.root, record, relative_path=relative_path
            )
        except ArtifactContentError:
            raise
        except ScorecardEvaluationError as exc:
            raise ArtifactContentError(
                code="checksum_mismatch",
                message=str(exc),
                status=409,
            ) from exc

    def list_all(self, *, run_id: str | None = None) -> list[dict[str, Any]]:
        latest: dict[str, ScorecardRecord] = {}
        for entry in self.store.list_entries():
            latest[entry.scorecard_id] = entry
        items = [_record_to_public_dict(self.root, e) for e in latest.values()]
        if run_id:
            items = [i for i in items if i["run_id"] == run_id]
        items.sort(key=lambda i: i["evaluated_at"], reverse=True)
        return items

    def invalidate(self, scorecard_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        scorecard_id = assert_safe_id(scorecard_id, field="scorecard_id")
        reason = str(payload.get("reason") or "").strip()
        if not reason:
            raise ResearchWriteError(
                "reason ist erforderlich", field_errors={"reason": "erforderlich"}
            )
        actor = str(payload.get("actor") or "api").strip() or "api"
        try:
            self.store.invalidate(scorecard_id, reason=reason, actor=actor)
        except KeyError as exc:
            raise KeyError(scorecard_id) from exc
        except ValueError as exc:
            raise ResearchWriteError(
                str(exc), field_errors={"scorecard_id": str(exc)}
            ) from exc
        record = self.store.get(scorecard_id)
        assert record is not None
        return _record_to_public_dict(self.root, record, fail_closed_active=False)

    def list_policies(self) -> list[dict[str, Any]]:
        return [
            _policy_to_public_dict(get_scorecard_policy(v))
            for v in list_scorecard_policy_versions()
        ]
