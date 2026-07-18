"""P4.9 versioned regime + transition classifier (Issue #285)."""

from __future__ import annotations

from research.regime.artifacts import (
    REGIME_LABELS_FILENAME,
    REGIME_LABELS_SCHEMA_VERSION,
    RegimeArtifactError,
    RegimeClassificationResult,
    classify_closes,
    classify_regime_series,
    compute_bars_content_hash,
    compute_classification_id,
    verify_regime_labels_seal,
    write_regime_labels_artifact,
)
from research.regime.classifier import (
    RegimeClassifier,
    RegimeClassifierError,
    compute_classifier_content_hash,
    get_classifier,
    list_classifier_versions,
    verify_classifier_content_hash,
)
from research.regime.labeling import (
    DayLabel,
    PeriodLabel,
    PriceBar,
    bars_from_closes,
    label_days,
    label_periods,
    regime_distribution,
)
from research.regime.transitions import (
    DayEventLabel,
    PeriodTransition,
    detect_period_transitions,
    directed_transition_id,
    label_day_events,
)

__all__ = [
    "REGIME_LABELS_FILENAME",
    "REGIME_LABELS_SCHEMA_VERSION",
    "DayEventLabel",
    "DayLabel",
    "PeriodLabel",
    "PeriodTransition",
    "PriceBar",
    "RegimeArtifactError",
    "RegimeClassificationResult",
    "RegimeClassifier",
    "RegimeClassifierError",
    "bars_from_closes",
    "classify_closes",
    "classify_regime_series",
    "compute_bars_content_hash",
    "compute_classification_id",
    "compute_classifier_content_hash",
    "detect_period_transitions",
    "directed_transition_id",
    "get_classifier",
    "label_day_events",
    "label_days",
    "label_periods",
    "list_classifier_versions",
    "regime_distribution",
    "verify_classifier_content_hash",
    "verify_regime_labels_seal",
    "write_regime_labels_artifact",
]
