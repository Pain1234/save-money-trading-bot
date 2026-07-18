"""Scorecard integrity profile + critical gate categories (Issue #286)."""

from __future__ import annotations

from pathlib import Path

import pytest
from research import gate_policy as gp
from research.gate_evaluator import (
    GateEvaluationResult,
    GateEvaluator,
    GateRunRecord,
    IntegrityCheckResult,
    quality_scores_permitted,
)
from research.gate_policy import (
    POLICY_1_0_CONTENT_HASH,
    compute_policy_content_hash,
    is_critical_category,
)

# Match test_gate_evaluator.py deploy-pin for .git-less evaluation roots.
_EVAL_SHA = "a" * 40

_DEFERRED_INTEGRITY_NAMES = frozenset(
    {
        "look_ahead_leakage",
        "accounting_fee_spec_identity",
        "regime_assignment_coverage",
    }
)


@pytest.fixture(autouse=True)
def _pin_evaluation_git_sha(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RESEARCH_EVALUATION_GIT_SHA", _EVAL_SHA)
    monkeypatch.delenv("RAILWAY_GIT_COMMIT_SHA", raising=False)


def _completed_run_helpers():
    from tests.research import test_gate_evaluator as te

    return te._completed_run, te._evaluation_image_root


def test_policy_1_0_content_hash_pinned_pre_286_value() -> None:
    """Frozen #248 policy 1.0 hash must not drift when categories are added."""
    policy = gp.get_policy("1.0")
    assert all(g.category == "" for g in policy.gates)
    # Canonical dict omits empty category — shape matches pre-#286.
    assert set(policy.gates[0].to_dict()) == {
        "name",
        "metric",
        "comparator",
        "threshold",
        "description",
    }
    digest = compute_policy_content_hash(policy)
    assert digest == POLICY_1_0_CONTENT_HASH
    assert POLICY_1_0_CONTENT_HASH == (
        "a589305b86745cb7ae1e1dde4b8e94e8dc6b6a8fd38a711d44f28415d54070c5"
    )


def test_policy_1_1_registers_critical_categories() -> None:
    assert "1.1" in gp.list_policy_versions()
    policy = gp.get_policy("1.1")
    assert policy.version == "1.1"
    assert compute_policy_content_hash(policy) != compute_policy_content_hash(
        gp.get_policy("1.0")
    )
    categories = {g.category for g in policy.gates}
    assert "sample_sufficiency" in categories
    assert "oos_net" in categories
    assert "drawdown" in categories
    assert "walk_forward" in categories
    assert "cost_stress" in categories
    assert "parameter_fragility" in categories
    assert "bootstrap" in categories
    assert all(is_critical_category(g.category) for g in policy.gates)


def test_missing_evidence_outcome_is_not_available_never_pass(tmp_path: Path) -> None:
    _completed_run, _evaluation_image_root = _completed_run_helpers()
    root, _experiment_id, run_id = _completed_run(tmp_path)
    evaluator = GateEvaluator(root, repo_root=_evaluation_image_root(root))
    record = evaluator.evaluate(run_id=run_id, policy_version="1.1")

    missing = [g for g in record.gates if g.measured_value is None]
    assert missing, "fixture without robustness should leave some metrics unbound"
    for gate in missing:
        assert gate.outcome == "NOT_AVAILABLE"
        assert gate.passed is False
        assert "never PASS" in gate.reason
    assert record.overall_status == "fail"
    assert all(g.category for g in record.gates)


def test_unimplemented_mandatory_checks_yield_not_verifiable(tmp_path: Path) -> None:
    """Fail-closed: missing automated verifiers must not produce VALID (#286)."""
    _completed_run, _evaluation_image_root = _completed_run_helpers()
    root, _experiment_id, run_id = _completed_run(tmp_path)
    evaluator = GateEvaluator(root, repo_root=_evaluation_image_root(root))
    record = evaluator.evaluate(run_id=run_id, policy_version="1.1")

    assert record.integrity_status == "NOT_VERIFIABLE"
    deferred = {c.name: c for c in record.integrity_checks if c.name in _DEFERRED_INTEGRITY_NAMES}
    assert deferred.keys() == _DEFERRED_INTEGRITY_NAMES
    assert all(c.status == "not_verifiable" for c in deferred.values())
    assert quality_scores_permitted(record) is False


def test_integrity_valid_permits_quality_scores_when_all_checks_pass() -> None:
    record = GateRunRecord(
        schema_version="1.1",
        gate_run_id="gate_valid",
        policy_version="1.1",
        policy_content_hash="a" * 64,
        evaluated_at="2024-01-01T00:00:00.000000Z",
        run_code_commit="0" * 40,
        evaluation_code_commit="0" * 40,
        experiment_id="exp_x",
        run_id="run_x",
        robustness_run_ids=(),
        dataset_id="ds_x",
        dataset_content_hash="b" * 64,
        artifact_checksums={"metrics.json": "c" * 64},
        measurements={"net_pnl": "1"},
        gates=(
            GateEvaluationResult(
                name="net_pnl_non_negative",
                threshold="0",
                measured_value="1",
                passed=True,
                reason="pass",
                outcome="PASS",
                category="oos_net",
            ),
        ),
        overall_status="pass",
        integrity_status="VALID",
        integrity_checks=(
            IntegrityCheckResult(name="dataset_binding", status="pass", reason="ok"),
        ),
    )
    assert quality_scores_permitted(record) is True


def test_integrity_invalid_blocks_quality_scores() -> None:
    record = GateRunRecord(
        schema_version="1.1",
        gate_run_id="gate_invalid",
        policy_version="1.1",
        policy_content_hash="a" * 64,
        evaluated_at="2024-01-01T00:00:00.000000Z",
        run_code_commit="0" * 40,
        evaluation_code_commit="0" * 40,
        experiment_id="exp_x",
        run_id="run_x",
        robustness_run_ids=(),
        dataset_id="ds_x",
        dataset_content_hash="b" * 64,
        artifact_checksums={"metrics.json": "c" * 64},
        measurements={"net_pnl": "1"},
        gates=(
            GateEvaluationResult(
                name="net_pnl_non_negative",
                threshold="0",
                measured_value="1",
                passed=True,
                reason="pass",
                outcome="PASS",
                category="oos_net",
            ),
        ),
        overall_status="pass",
        integrity_status="INVALID",
        integrity_checks=(
            IntegrityCheckResult(
                name="dataset_binding",
                status="fail",
                reason="fixture",
            ),
        ),
    )
    assert quality_scores_permitted(record) is False


def test_integrity_not_verifiable_blocks_quality_scores() -> None:
    record = GateRunRecord(
        schema_version="1.0",
        gate_run_id="gate_legacy",
        policy_version="1.0",
        policy_content_hash="a" * 64,
        evaluated_at="2024-01-01T00:00:00.000000Z",
        run_code_commit="0" * 40,
        evaluation_code_commit="0" * 40,
        experiment_id="exp_x",
        run_id="run_x",
        robustness_run_ids=(),
        dataset_id="ds_x",
        dataset_content_hash="b" * 64,
        artifact_checksums={"metrics.json": "c" * 64},
        measurements={},
        gates=(),
        overall_status="fail",
    )
    # Default / legacy missing profile → NOT_VERIFIABLE.
    assert record.integrity_status == "NOT_VERIFIABLE"
    assert quality_scores_permitted(record) is False

    round_trip = GateRunRecord.from_dict(
        {
            "schema_version": "1.0",
            "gate_run_id": "gate_legacy",
            "policy_version": "1.0",
            "policy_content_hash": "a" * 64,
            "evaluated_at": "2024-01-01T00:00:00.000000Z",
            "run_code_commit": "0" * 40,
            "evaluation_code_commit": "0" * 40,
            "experiment_id": "exp_x",
            "run_id": "run_x",
            "robustness_run_ids": [],
            "dataset_id": "ds_x",
            "dataset_content_hash": "b" * 64,
            "artifact_checksums": {"metrics.json": "c" * 64},
            "measurements": {},
            "gates": [
                {
                    "name": "min_closed_trades",
                    "threshold": "10",
                    "measured_value": None,
                    "passed": False,
                    "reason": "no evidence",
                }
            ],
            "overall_status": "fail",
            "promotion_action": "none",
            "status": "active",
        }
    )
    assert round_trip.integrity_status == "NOT_VERIFIABLE"
    assert round_trip.gates[0].outcome == "NOT_AVAILABLE"
    assert round_trip.gates[0].passed is False
    assert quality_scores_permitted(round_trip) is False


def test_from_dict_derives_passed_from_outcome_when_contradictory() -> None:
    gate = GateEvaluationResult.from_dict(
        {
            "name": "net_pnl_non_negative",
            "threshold": "0",
            "measured_value": "-1",
            "passed": True,  # contradictory stale client field
            "reason": "should fail",
            "outcome": "FAIL",
            "category": "oos_net",
        }
    )
    assert gate.outcome == "FAIL"
    assert gate.passed is False

    missing = GateEvaluationResult.from_dict(
        {
            "name": "walk_forward_fold_pass_ratio",
            "threshold": "0.5",
            "measured_value": None,
            "passed": True,
            "reason": "stale",
            "outcome": "NOT_AVAILABLE",
        }
    )
    assert missing.outcome == "NOT_AVAILABLE"
    assert missing.passed is False


def test_gate_result_rejects_contradictory_passed_vs_outcome() -> None:
    with pytest.raises(ValueError, match="contradicts"):
        GateEvaluationResult(
            name="max_drawdown_floor",
            threshold="-0.5",
            measured_value="-0.9",
            passed=True,
            reason="fail",
            outcome="FAIL",
            category="drawdown",
        )


def test_invalidated_record_blocks_quality_scores(tmp_path: Path) -> None:
    _completed_run, _evaluation_image_root = _completed_run_helpers()
    root, _experiment_id, run_id = _completed_run(tmp_path)
    evaluator = GateEvaluator(root, repo_root=_evaluation_image_root(root))
    record = evaluator.evaluate(run_id=run_id, policy_version="1.1")
    # Evaluate path is NOT_VERIFIABLE until deferred checks are implemented;
    # still assert invalidate blocks even if a future path becomes VALID.
    active_permitted = quality_scores_permitted(record)
    evaluator.store.invalidate(record.gate_run_id, reason="fixture", actor="test")
    invalidated = evaluator.store.get(record.gate_run_id)
    assert invalidated is not None
    assert invalidated.status == "invalidated"
    assert quality_scores_permitted(invalidated) is False
    assert active_permitted is False or invalidated.integrity_status == record.integrity_status


def test_append_only_still_holds_for_policy_1_1(tmp_path: Path) -> None:
    _completed_run, _evaluation_image_root = _completed_run_helpers()
    root, _experiment_id, run_id = _completed_run(tmp_path)
    evaluator = GateEvaluator(root, repo_root=_evaluation_image_root(root))
    first = evaluator.evaluate(run_id=run_id, policy_version="1.1")
    second = evaluator.evaluate(run_id=run_id, policy_version="1.1")
    assert first.gate_run_id == second.gate_run_id
    assert first.integrity_status == "NOT_VERIFIABLE"
    lines = evaluator.store.path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1


def test_promotion_action_remains_none(tmp_path: Path) -> None:
    _completed_run, _evaluation_image_root = _completed_run_helpers()
    root, _experiment_id, run_id = _completed_run(tmp_path)
    evaluator = GateEvaluator(root, repo_root=_evaluation_image_root(root))
    record = evaluator.evaluate(run_id=run_id, policy_version="1.1")
    assert record.promotion_action == "none"
