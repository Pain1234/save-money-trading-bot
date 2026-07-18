"""Unit tests for the Validation Study record + append-only store (#249 / P4.7d).

Mirrors ``tests/research/test_gate_evaluator.py`` (#248) for the append-only
persistence contract. Pure model/store tests — no experiment runner needed.
Public/synthetic data only; no private Strategy V1 numbers.
"""

from __future__ import annotations

from pathlib import Path

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
)


def _pin(
    *,
    experiment_id: str = "exp_synthetic_base",
    run_id: str = "run_synthetic_base",
) -> PinnedRunEvidence:
    return PinnedRunEvidence(
        experiment_id=experiment_id,
        run_id=run_id,
        checksums_digest=checksums_digest({"metrics.json": "abc"}),
        dataset_id="ds_synthetic",
        dataset_content_hash="0" * 64,
        git_commit="1" * 40,
    )


def _snapshot(
    *,
    primary: PinnedRunEvidence | None = None,
    additional: tuple[PinnedRunEvidence, ...] = (),
    robustness: tuple[PinnedRobustnessEvidence, ...] = (
        PinnedRobustnessEvidence(robustness_id="rob_synthetic_wf", manifest_hash="a" * 64),
    ),
    gates: tuple[PinnedGateEvidence, ...] = (
        PinnedGateEvidence(gate_run_id="gate_synthetic", content_hash="b" * 64),
    ),
) -> StudyEvidenceSnapshot:
    primary_pin = primary or _pin()
    snapshot_id = StudyEvidenceSnapshot.compute_snapshot_id(
        primary=primary_pin,
        additional=additional,
        robustness=robustness,
        gates=gates,
    )
    return StudyEvidenceSnapshot(
        snapshot_id=snapshot_id,
        primary=primary_pin,
        additional=additional,
        robustness=robustness,
        gates=gates,
    )


def _record(
    study_id: str,
    *,
    status: str = "open",
    decision: StudyDecision | None = None,
    snapshot: StudyEvidenceSnapshot | None = None,
) -> StudyRecord:
    snap = snapshot or _snapshot()
    return StudyRecord(
        schema_version=VALIDATION_STUDY_SCHEMA_VERSION,
        study_id=study_id,
        created_at="2024-01-01T00:00:00.000000Z",
        name="synthetic study",
        strategy_id="trend_v1",
        strategy_version="1.0.0",
        experiment_id=snap.primary.experiment_id,
        run_id=snap.primary.run_id,
        additional_experiment_ids=tuple(p.experiment_id for p in snap.additional),
        additional_run_ids=tuple(p.run_id for p in snap.additional),
        robustness_ids=tuple(r.robustness_id for r in snap.robustness),
        gate_run_ids=tuple(g.gate_run_id for g in snap.gates),
        evidence_snapshot=snap,
        notes="fixture",
        status=status,  # type: ignore[arg-type]
        decision=decision,
    )


def test_compute_study_id_is_deterministic_and_order_independent() -> None:
    a = compute_study_id(
        experiment_id="exp_1",
        run_id="run_1",
        additional_experiment_ids=["exp_2", "exp_3"],
        additional_run_ids=["run_2", "run_3"],
        robustness_ids=["rob_2", "rob_1"],
        gate_run_ids=["gate_1"],
        evidence_snapshot_id="evsnap_aaa",
    )
    b = compute_study_id(
        experiment_id="exp_1",
        run_id="run_1",
        additional_experiment_ids=["exp_3", "exp_2"],
        additional_run_ids=["run_3", "run_2"],
        robustness_ids=["rob_1", "rob_2"],
        gate_run_ids=["gate_1"],
        evidence_snapshot_id="evsnap_aaa",
    )
    assert a == b
    assert a.startswith("study_")
    assert len(a) == len("study_") + 64


def test_compute_study_id_changes_with_additional_evidence() -> None:
    base = compute_study_id(
        experiment_id="exp_1",
        run_id="run_1",
        additional_experiment_ids=[],
        additional_run_ids=[],
        robustness_ids=["rob_1"],
        gate_run_ids=[],
        evidence_snapshot_id="evsnap_aaa",
    )
    with_gate = compute_study_id(
        experiment_id="exp_1",
        run_id="run_1",
        additional_experiment_ids=[],
        additional_run_ids=[],
        robustness_ids=["rob_1"],
        gate_run_ids=["gate_1"],
        evidence_snapshot_id="evsnap_bbb",
    )
    assert base != with_gate


def test_compute_study_id_changes_when_run_pin_changes() -> None:
    a = compute_study_id(
        experiment_id="exp_1",
        run_id="run_A",
        additional_experiment_ids=[],
        additional_run_ids=[],
        robustness_ids=[],
        gate_run_ids=[],
        evidence_snapshot_id="evsnap_a",
    )
    b = compute_study_id(
        experiment_id="exp_1",
        run_id="run_B",
        additional_experiment_ids=[],
        additional_run_ids=[],
        robustness_ids=[],
        gate_run_ids=[],
        evidence_snapshot_id="evsnap_b",
    )
    assert a != b


def test_study_record_round_trips_through_dict() -> None:
    record = _record("study_abc")
    rebuilt = StudyRecord.from_dict(record.to_dict())
    assert rebuilt == record


def test_store_append_and_get(tmp_path: Path) -> None:
    store = StudyStore(tmp_path)
    record = _record("study_abc")
    store.append(record)

    fetched = store.get("study_abc")
    assert fetched is not None
    assert fetched.status == "open"
    assert fetched.decision is None
    assert fetched.evidence_snapshot.snapshot_id.startswith("evsnap_")
    assert store.path.is_file()


def test_store_append_rejects_duplicate_study_id(tmp_path: Path) -> None:
    store = StudyStore(tmp_path)
    store.append(_record("study_dup"))
    try:
        store.append(_record("study_dup"))
    except ValueError as exc:
        assert "duplicate study_id" in str(exc)
    else:
        raise AssertionError("expected duplicate study_id to be rejected")


def test_record_decision_appends_superseding_record_not_mutating_original(
    tmp_path: Path,
) -> None:
    store = StudyStore(tmp_path)
    record = _record("study_decide")
    store.append(record)

    decision = StudyDecision(
        outcome="accept",
        rationale="synthetic gates passed",
        decided_by="tester",
        decided_at="2024-01-02T00:00:00.000000Z",
        evidence_snapshot_id=record.evidence_snapshot.snapshot_id,
    )
    updated = store.record_decision("study_decide", decision, actor="tester")
    assert updated.status == "decided"
    assert updated.decision == decision
    assert updated.decision is not None
    assert updated.decision.evidence_snapshot_id == record.evidence_snapshot.snapshot_id

    # Append-only: both the original ("open") and superseding ("decided")
    # lines remain on disk — the original is never rewritten in place.
    raw_lines = store.path.read_text(encoding="utf-8").splitlines()
    assert len(raw_lines) == 2

    # ``get`` returns the latest (decided) record.
    latest = store.get("study_decide")
    assert latest is not None
    assert latest.status == "decided"
    assert latest.decision is not None
    assert latest.decision.outcome == "accept"

    # Audit sidecar records the decision provenance separately.
    sidecar = store.decisions_dir / "study_decide.jsonl"
    assert sidecar.is_file()
    assert "synthetic gates passed" in sidecar.read_text(encoding="utf-8")


def test_record_decision_rejects_mismatched_snapshot_id(tmp_path: Path) -> None:
    store = StudyStore(tmp_path)
    store.append(_record("study_snap"))
    decision = StudyDecision(
        outcome="accept",
        rationale="synthetic",
        decided_by="tester",
        decided_at="2024-01-02T00:00:00.000000Z",
        evidence_snapshot_id="evsnap_wrong",
    )
    try:
        store.record_decision("study_snap", decision, actor="tester")
    except ValueError as exc:
        assert "evidence_snapshot_id" in str(exc)
    else:
        raise AssertionError("expected mismatched snapshot_id to be rejected")


def test_record_decision_is_one_shot(tmp_path: Path) -> None:
    """A decided study cannot be re-decided — new evidence needs a new Study,

    matching ``AGENTS.md`` §8 (never overwrite historical research)."""
    store = StudyStore(tmp_path)
    record = _record("study_once")
    store.append(record)
    decision = StudyDecision(
        outcome="reject",
        rationale="synthetic gate failed",
        decided_by="tester",
        decided_at="2024-01-02T00:00:00.000000Z",
        evidence_snapshot_id=record.evidence_snapshot.snapshot_id,
    )
    store.record_decision("study_once", decision, actor="tester")

    try:
        store.record_decision("study_once", decision, actor="tester")
    except ValueError as exc:
        assert "already decided" in str(exc)
    else:
        raise AssertionError("expected re-deciding a decided study to be rejected")


def test_record_decision_unknown_study_raises_key_error(tmp_path: Path) -> None:
    store = StudyStore(tmp_path)
    decision = StudyDecision(
        outcome="accept",
        rationale="n/a",
        decided_by="tester",
        decided_at="2024-01-02T00:00:00.000000Z",
        evidence_snapshot_id="evsnap_missing",
    )
    try:
        store.record_decision("study_missing", decision, actor="tester")
    except KeyError:
        pass
    else:
        raise AssertionError("expected KeyError for unknown study_id")


def test_list_latest_deduplicates_by_study_id(tmp_path: Path) -> None:
    store = StudyStore(tmp_path)
    store.append(_record("study_a"))
    store.append(_record("study_b"))
    record_a = store.get("study_a")
    assert record_a is not None
    decision = StudyDecision(
        outcome="inconclusive",
        rationale="insufficient sample",
        decided_by="tester",
        decided_at="2024-01-02T00:00:00.000000Z",
        evidence_snapshot_id=record_a.evidence_snapshot.snapshot_id,
    )
    store.record_decision("study_a", decision, actor="tester")

    latest = store.list_latest()
    assert {r.study_id for r in latest} == {"study_a", "study_b"}
    by_id = {r.study_id: r for r in latest}
    assert by_id["study_a"].status == "decided"
    assert by_id["study_b"].status == "open"


def test_decision_promotion_action_field_does_not_exist() -> None:
    """Leakage-negative: a Study decision has no promotion-trigger field at all.

    Mirrors ``GateRunRecord.promotion_action`` always being ``"none"`` (#248)
    — here there is no such field because no code path here ever calls into
    ``paper_trading`` or a live order surface (#249 non-scope).
    """
    decision = StudyDecision(
        outcome="accept",
        rationale="synthetic",
        decided_by="tester",
        decided_at="2024-01-02T00:00:00.000000Z",
        evidence_snapshot_id="evsnap_x",
    )
    assert set(decision.to_dict()) == {
        "outcome",
        "rationale",
        "decided_by",
        "decided_at",
        "evidence_snapshot_id",
    }
