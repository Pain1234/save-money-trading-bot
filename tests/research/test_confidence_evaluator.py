"""Unit tests for evidence-confidence policy + evaluator (#288)."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest
from research.confidence import (
    CONFIDENCE_POLICY_1_0_CONTENT_HASH,
    ConfidenceEvidenceInputs,
    ConfidencePolicyError,
    compute_confidence_policy_content_hash,
    evaluate_confidence,
    get_confidence_policy,
    verify_confidence_policy_content_hash,
    verify_confidence_profile_seal,
    write_confidence_profile_artifact,
)
from research.confidence.artifacts import ConfidenceArtifactError

# Review-pinned literal (must match CONFIDENCE_POLICY_1_0_CONTENT_HASH exactly).
_PINNED_POLICY_1_0_HASH = (
    "22748e176aa64ed36e01ac1911ac73b2314cb9ad22612b2206f80faec190d706"
)


def _base_inputs(**overrides: object) -> ConfidenceEvidenceInputs:
    # series=400, block=5 → effective_block_count=80 → bootstrap HIGH under policy 1.0
    payload: dict[str, object] = {
        "run_id": "run_x",
        "experiment_id": "exp_x",
        "dataset_id": "ds_x",
        "dataset_content_hash": "b" * 64,
        "run_status": "complete",
        "closed_trades": 120,
        "equity_periods": 300,
        "walk_forward_folds_complete": 5,
        "walk_forward_fold_pass_ratio": Decimal("0.8"),
        "parameter_neighbors_complete": 8,
        "parameter_neighbor_pass_ratio": Decimal("0.75"),
        "bootstrap_series_length": 400,
        "bootstrap_block_length": 5,
        "bootstrap_assessed": True,
        "regime_coverage_ratio": Decimal("0.97"),
        "regime_evidence_status": "OK",
        "gate_integrity_status": "VALID",
        "robustness_run_ids": ("rob_a",),
        "multiple_testing_metadata": {"variants_tested": 3, "note": "fixture"},
    }
    payload.update(overrides)
    return ConfidenceEvidenceInputs(**payload)  # type: ignore[arg-type]


def test_policy_1_0_content_hash_is_pinned_literal() -> None:
    policy = get_confidence_policy("1.0")
    digest = compute_confidence_policy_content_hash(policy)
    assert digest == _PINNED_POLICY_1_0_HASH
    assert CONFIDENCE_POLICY_1_0_CONTENT_HASH == _PINNED_POLICY_1_0_HASH
    assert len(digest) == 64
    verify_confidence_policy_content_hash("1.0", _PINNED_POLICY_1_0_HASH)


def test_policy_content_hash_rejects_stale() -> None:
    with pytest.raises(ConfidencePolicyError, match="content hash mismatch"):
        verify_confidence_policy_content_hash("1.0", "0" * 64)


def test_high_n_synthetic_case_is_high() -> None:
    result = evaluate_confidence(_base_inputs())
    assert result.overall_label == "HIGH"
    assert result.decision_binding is False
    assert result.auto_promotion is False
    by_name = {d.name: d for d in result.dimensions}
    assert by_name["trade_sample"].label == "HIGH"
    assert by_name["trade_sample"].measured_value == "120"
    assert by_name["bootstrap_uncertainty"].measured_value == "80"
    assert by_name["bootstrap_uncertainty"].raw_inputs["effective_block_count"] == 80
    assert any(lim.code == "serial_dependence" for lim in result.limitations)
    assert any(
        lim.code == "multiple_testing" and lim.status == "DOCUMENTED"
        for lim in result.limitations
    )


def test_insufficient_trade_sample() -> None:
    result = evaluate_confidence(_base_inputs(closed_trades=3))
    by_name = {d.name: d for d in result.dimensions}
    assert by_name["trade_sample"].label == "INSUFFICIENT"
    assert result.overall_label == "INSUFFICIENT"


def test_missing_closed_trades_is_not_available_never_zero() -> None:
    result = evaluate_confidence(_base_inputs(closed_trades=None))
    by_name = {d.name: d for d in result.dimensions}
    assert by_name["trade_sample"].label == "NOT_AVAILABLE"
    assert result.overall_label == "NOT_AVAILABLE"
    assert "never coerce" in by_name["trade_sample"].reason


def test_incomplete_run_is_not_available() -> None:
    result = evaluate_confidence(_base_inputs(run_status="failed", closed_trades=200))
    assert result.overall_label == "NOT_AVAILABLE"


def test_invalid_integrity_blocks_confidence_label() -> None:
    result = evaluate_confidence(_base_inputs(gate_integrity_status="INVALID"))
    assert result.overall_label == "NOT_AVAILABLE"
    assert "INVALID" in result.overall_reason


def test_missing_bootstrap_caps_high_to_medium() -> None:
    result = evaluate_confidence(
        _base_inputs(
            bootstrap_assessed=False,
            bootstrap_series_length=None,
            bootstrap_block_length=None,
            multiple_testing_metadata={"variants_tested": 3},
        )
    )
    by_name = {d.name: d for d in result.dimensions}
    assert by_name["bootstrap_uncertainty"].label == "NOT_AVAILABLE"
    assert by_name["trade_sample"].label == "HIGH"
    assert result.overall_label == "MEDIUM"
    assert "capped" in result.overall_reason
    serial = next(lim for lim in result.limitations if lim.code == "serial_dependence")
    assert serial.status == "LIMITATION"


def test_missing_multiple_testing_docs_caps_high() -> None:
    result = evaluate_confidence(_base_inputs(multiple_testing_metadata=None))
    assert result.overall_label == "MEDIUM"
    assert "multiple_testing" in result.overall_reason


def test_bootstrap_uses_effective_block_count_not_raw_series() -> None:
    # 80/5 → 16 effective blocks → LOW (2<=16<20), not HIGH from raw 80.
    result = evaluate_confidence(
        _base_inputs(bootstrap_series_length=80, bootstrap_block_length=5)
    )
    boot = next(d for d in result.dimensions if d.name == "bootstrap_uncertainty")
    assert boot.measured_value == "16"
    assert boot.label == "LOW"
    assert boot.raw_inputs["effective_block_count"] == 16


def test_bootstrap_assessed_without_block_length_is_not_available() -> None:
    result = evaluate_confidence(
        _base_inputs(bootstrap_assessed=True, bootstrap_block_length=None)
    )
    boot = next(d for d in result.dimensions if d.name == "bootstrap_uncertainty")
    assert boot.label == "NOT_AVAILABLE"
    assert result.overall_label == "MEDIUM"


def test_confidence_id_changes_when_inputs_change() -> None:
    high = evaluate_confidence(_base_inputs(closed_trades=120))
    low = evaluate_confidence(_base_inputs(closed_trades=3))
    assert high.confidence_id != low.confidence_id
    assert high.inputs_summary["evidence_content_hash"] != low.inputs_summary[
        "evidence_content_hash"
    ]


def test_raw_inputs_visible_on_dimensions() -> None:
    result = evaluate_confidence(_base_inputs(closed_trades=45))
    trade = next(d for d in result.dimensions if d.name == "trade_sample")
    assert trade.raw_inputs["closed_trades"] == 45
    assert trade.label == "MEDIUM"
    assert "closed_trades" in result.inputs_summary


def test_no_manual_confidence_override_field() -> None:
    fields = ConfidenceEvidenceInputs.__dataclass_fields__
    assert "confidence" not in fields
    assert "manual_confidence" not in fields
    assert "overall_label" not in fields


def test_artifact_write_once_and_seal(tmp_path: Path) -> None:
    result = evaluate_confidence(_base_inputs())
    path = write_confidence_profile_artifact(tmp_path, result.to_artifact())
    assert path.name == "confidence_profile.json"
    digest = verify_confidence_profile_seal(tmp_path)
    assert len(digest) == 64
    with pytest.raises(ConfidenceArtifactError, match="refusing to overwrite"):
        write_confidence_profile_artifact(tmp_path, result.to_artifact())


def test_unknown_policy_version_raises() -> None:
    with pytest.raises(Exception, match="unknown confidence policy"):
        evaluate_confidence(_base_inputs(), policy_version="9.9")
