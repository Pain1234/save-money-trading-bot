"""Unit/integration tests for scorecard evaluate + store (#291)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from research.scorecard_evaluator import (
    ScorecardEvaluationError,
    ScorecardEvaluator,
    ScorecardResultStore,
    scorecard_evidence_content_hash,
    verify_scorecard_record_artifact_checksums,
)
from research.scorecard_policy import (
    SCORECARD_POLICY_1_0_CONTENT_HASH,
    compute_scorecard_policy_content_hash,
    get_scorecard_policy,
)

from tests.research import test_gate_evaluator as te

_PINNED = "feb34430dae49a67833e580b99f05c79ba55e46d8af9f32135c35d7b68ab9e4b"


@pytest.fixture(autouse=True)
def _pin_evaluation_git_sha(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RESEARCH_EVALUATION_GIT_SHA", "a" * 40)
    monkeypatch.delenv("RAILWAY_GIT_COMMIT_SHA", raising=False)


def test_scorecard_policy_1_0_hash_pinned_literal() -> None:
    digest = compute_scorecard_policy_content_hash(get_scorecard_policy("1.0"))
    assert digest == _PINNED
    assert SCORECARD_POLICY_1_0_CONTENT_HASH == _PINNED


def test_scorecard_evaluate_idempotent_and_pins_layers(tmp_path: Path) -> None:
    root, _experiment_id, run_id = te._completed_run(tmp_path)
    evaluator = ScorecardEvaluator(root, repo_root=te._evaluation_image_root(root))
    first = evaluator.evaluate(run_id=run_id, policy_version="1.0")
    second = evaluator.evaluate(run_id=run_id, policy_version="1.0")
    assert first.scorecard_id == second.scorecard_id
    assert first.scorecard_id.startswith("sc_")
    assert first.schema_version == "1.0"
    assert first.promotion_action == "none"
    assert first.auto_promotion is False
    assert first.decision_binding is False
    assert first.layer_refs.get("classification_id")
    assert first.layer_refs.get("quality_id")
    assert first.layer_refs.get("behaviour_id")
    assert first.layer_refs.get("confidence_id")
    assert first.global_profile["parameter_area"]["status"] == "NOT_AVAILABLE"
    assert first.dataset_id
    assert first.dataset_content_hash
    assert first.run_code_commit
    assert first.evaluation_code_commit
    assert first.artifact_checksums
    assert first.evidence_content_hash == scorecard_evidence_content_hash(first)
    lines = evaluator.store.path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1


def test_scorecard_invalidate_append_only(tmp_path: Path) -> None:
    root, _experiment_id, run_id = te._completed_run(tmp_path)
    evaluator = ScorecardEvaluator(root, repo_root=te._evaluation_image_root(root))
    record = evaluator.evaluate(run_id=run_id, policy_version="1.0")
    store = ScorecardResultStore(root)
    store.invalidate(record.scorecard_id, reason="fixture", actor="test")
    latest = store.get(record.scorecard_id)
    assert latest is not None
    assert latest.status == "invalidated"
    assert latest.invalidation_reason == "fixture"
    assert len(store.list_entries()) == 2


def test_scorecard_evaluate_refuses_reactivation_after_invalidate(tmp_path: Path) -> None:
    root, _experiment_id, run_id = te._completed_run(tmp_path)
    evaluator = ScorecardEvaluator(root, repo_root=te._evaluation_image_root(root))
    record = evaluator.evaluate(run_id=run_id, policy_version="1.0")
    ScorecardResultStore(root).invalidate(record.scorecard_id, reason="fixture", actor="test")
    with pytest.raises(ScorecardEvaluationError, match="invalidated") as exc:
        evaluator.evaluate(run_id=run_id, policy_version="1.0")
    assert exc.value.field_errors.get("scorecard_id") == "invalidated"
    assert len(ScorecardResultStore(root).list_entries()) == 2


def test_scorecard_tampered_global_profile_fail_closed(tmp_path: Path) -> None:
    root, _experiment_id, run_id = te._completed_run(tmp_path)
    evaluator = ScorecardEvaluator(root, repo_root=te._evaluation_image_root(root))
    record = evaluator.evaluate(run_id=run_id, policy_version="1.0")
    lines = evaluator.store.path.read_text(encoding="utf-8").strip().splitlines()
    payload = json.loads(lines[0])
    payload["global_profile"] = {**payload["global_profile"], "tampered": True}
    evaluator.store.path.write_text(
        json.dumps(payload, sort_keys=True) + "\n", encoding="utf-8"
    )
    tampered = ScorecardResultStore(root).get(record.scorecard_id)
    assert tampered is not None
    with pytest.raises(ScorecardEvaluationError, match="evidence_content_hash"):
        verify_scorecard_record_artifact_checksums(root, tampered)


def test_scorecard_rejects_unknown_robustness_id(tmp_path: Path) -> None:
    root, _experiment_id, run_id = te._completed_run(tmp_path)
    evaluator = ScorecardEvaluator(root, repo_root=te._evaluation_image_root(root))
    with pytest.raises(ScorecardEvaluationError) as exc:
        evaluator.evaluate(
            run_id=run_id,
            policy_version="1.0",
            robustness_run_ids=["rob_missing_not_real"],
        )
    assert "robustness_run_ids" in exc.value.field_errors
