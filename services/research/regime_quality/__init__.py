"""P4.9 regime-level quality metrics (#287)."""

from __future__ import annotations

from research.regime_quality.artifacts import (
    RegimeMetricsArtifactError,
    verify_regime_metrics_seal,
    write_regime_metrics_artifact,
)
from research.regime_quality.availability import NOT_AVAILABLE, is_na, na
from research.regime_quality.evaluator import (
    REGIME_METRICS_FILENAME,
    REGIME_METRICS_SCHEMA_VERSION,
    RegimeQualityError,
    RegimeQualityResult,
    compute_quality_id,
    evaluate_regime_quality,
    evaluate_regime_quality_from_run_dir,
)
from research.regime_quality.metrics import RegimeSliceRaw, compute_slice_metrics
from research.regime_quality.scoring import (
    QualityScorePolicy,
    compute_score_policy_content_hash,
    get_score_policy,
    summarize_slice_score,
)

__all__ = [
    "NOT_AVAILABLE",
    "REGIME_METRICS_FILENAME",
    "REGIME_METRICS_SCHEMA_VERSION",
    "QualityScorePolicy",
    "RegimeMetricsArtifactError",
    "RegimeQualityError",
    "RegimeQualityResult",
    "RegimeSliceRaw",
    "compute_quality_id",
    "compute_score_policy_content_hash",
    "compute_slice_metrics",
    "evaluate_regime_quality",
    "evaluate_regime_quality_from_run_dir",
    "get_score_policy",
    "is_na",
    "na",
    "summarize_slice_score",
    "verify_regime_metrics_seal",
    "write_regime_metrics_artifact",
]
