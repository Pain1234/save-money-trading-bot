"""Versioned regime classifier definition + content hashing (Issue #285).

Mirrors the gate-policy pattern (#248): identity is ``classifier_version``
**and** the SHA-256 content hash of the full frozen definition. Silent edits
under the same version string fail closed via :func:`verify_classifier_content_hash`.

Generic example thresholds in version ``1.0`` are infrastructure defaults for
reproducible tests — **not** private Strategy V1 / P5 partition-B medians.
P5-03 (#199) High/Low vol remains the Strategy V1 evaluation contract; three-way
vol here is the P4.9 scorecard taxonomy. Binding freeze is [#294].
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass


class RegimeClassifierError(Exception):
    """Unknown classifier version or content-hash mismatch."""


@dataclass(frozen=True)
class RegimeClassifier:
    """Immutable, versioned regime + transition classification rules."""

    version: str
    description: str
    # Trend axis (#199 monthly return thresholds, public generic defaults).
    trend_bull_min: str
    trend_bear_max: str
    # Vol axis (three-way scorecard taxonomy; frozen absolute bounds).
    vol_low_max: str
    vol_high_min: str
    # Fail-closed sample floors / transition windows (bars = daily closes).
    min_bars_per_period: int
    transition_window_bars: int
    period: str = "calendar_month"
    schema_version: str = "1.0"

    def to_dict(self) -> dict[str, object]:
        return {
            "description": self.description,
            "min_bars_per_period": self.min_bars_per_period,
            "period": self.period,
            "schema_version": self.schema_version,
            "transition_window_bars": self.transition_window_bars,
            "trend_bear_max": self.trend_bear_max,
            "trend_bull_min": self.trend_bull_min,
            "version": self.version,
            "vol_high_min": self.vol_high_min,
            "vol_low_max": self.vol_low_max,
        }


def _canonical_json_bytes(payload: object) -> bytes:
    return json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def compute_classifier_content_hash(classifier: RegimeClassifier) -> str:
    """SHA-256 over the classifier's full semantic content."""
    return hashlib.sha256(_canonical_json_bytes(classifier.to_dict())).hexdigest()


# --- Registered classifier versions -----------------------------------------
# Extend by adding a NEW version key; never mutate an existing version in place.

_CLASSIFIER_REGISTRY: dict[str, RegimeClassifier] = {
    "1.0": RegimeClassifier(
        version="1.0",
        description=(
            "Generic P4.9 regime classifier: calendar-month trend "
            "(#199 +5%/-5%) and three-way vol bounds with explicit "
            "transition windows. Not the private P5 partition-B median; "
            "Strategy V1 freeze binding is #294."
        ),
        trend_bull_min="0.05",
        trend_bear_max="-0.05",
        # Generic daily-return stdev floors (illustrative public defaults).
        vol_low_max="0.015",
        vol_high_min="0.035",
        min_bars_per_period=5,
        transition_window_bars=5,
    ),
}


def get_classifier(version: str) -> RegimeClassifier:
    """Return a registered classifier version or raise."""
    try:
        return _CLASSIFIER_REGISTRY[version]
    except KeyError as exc:
        raise RegimeClassifierError(
            f"unknown classifier version: {version!r}"
        ) from exc


def list_classifier_versions() -> tuple[str, ...]:
    return tuple(sorted(_CLASSIFIER_REGISTRY))


def verify_classifier_content_hash(version: str, expected_hash: str) -> None:
    """Fail closed if the registered classifier no longer matches ``expected_hash``."""
    classifier = get_classifier(version)
    actual = compute_classifier_content_hash(classifier)
    if actual != expected_hash:
        raise RegimeClassifierError(
            f"classifier content hash mismatch for version {version!r}: "
            f"expected {expected_hash}, got {actual}"
        )
