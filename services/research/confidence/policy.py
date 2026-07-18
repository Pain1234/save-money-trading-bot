"""Versioned evidence-confidence policy (#288 / REGIME_SCORECARD Layer 3).

Thresholds are generic public example floors (aligned with gate policy 1.0
``min_closed_trades=10``), not private Strategy V1 / P5 numbers.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from decimal import Decimal
from typing import Literal

ConfidenceLabel = Literal[
    "HIGH",
    "MEDIUM",
    "LOW",
    "INSUFFICIENT",
    "NOT_AVAILABLE",
]

# Severity for aggregation (higher = stronger confidence). NOT_AVAILABLE is
# handled separately and does not participate in min-of-present aggregation.
_LABEL_RANK: dict[str, int] = {
    "INSUFFICIENT": 0,
    "LOW": 1,
    "MEDIUM": 2,
    "HIGH": 3,
}

ConfidenceDimensionName = Literal[
    "trade_sample",
    "time_coverage",
    "oos_folds",
    "parameter_plateau",
    "bootstrap_uncertainty",
    "regime_coverage",
]


class ConfidencePolicyError(Exception):
    """Unknown policy version or content-hash mismatch."""


@dataclass(frozen=True)
class ConfidenceDimensionFloors:
    """Inclusive floors for LOW / MEDIUM / HIGH bands.

    Mapping when a measured value is present:
    - ``value < low_floor`` → ``INSUFFICIENT``
    - ``low_floor <= value < medium_floor`` → ``LOW``
    - ``medium_floor <= value < high_floor`` → ``MEDIUM``
    - ``value >= high_floor`` → ``HIGH``

    Values are Decimal-as-string for stable content hashing.
    """

    name: ConfidenceDimensionName
    description: str
    low_floor: str
    medium_floor: str
    high_floor: str
    required: bool = False

    def to_dict(self) -> dict[str, object]:
        return {
            "description": self.description,
            "high_floor": self.high_floor,
            "low_floor": self.low_floor,
            "medium_floor": self.medium_floor,
            "name": self.name,
            "required": self.required,
        }


@dataclass(frozen=True)
class ConfidencePolicy:
    version: str
    description: str
    dimensions: tuple[ConfidenceDimensionFloors, ...]
    # Dimensions that must be present (not NOT_AVAILABLE) before overall HIGH.
    high_requires_dimensions: tuple[str, ...]
    # Limitation codes that must be status DOCUMENTED before overall HIGH.
    high_requires_limitations_documented: tuple[str, ...]
    aggregation: Literal["min_present_with_high_cap"] = "min_present_with_high_cap"
    # Cap applied when high_requires_* are unmet (never silent HIGH).
    high_cap_label: ConfidenceLabel = "MEDIUM"

    def to_dict(self) -> dict[str, object]:
        return {
            "aggregation": self.aggregation,
            "description": self.description,
            "dimensions": [d.to_dict() for d in self.dimensions],
            "high_cap_label": self.high_cap_label,
            "high_requires_dimensions": list(self.high_requires_dimensions),
            "high_requires_limitations_documented": list(
                self.high_requires_limitations_documented
            ),
            "version": self.version,
        }


def _canonical_json_bytes(payload: object) -> bytes:
    return json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def compute_confidence_policy_content_hash(policy: ConfidencePolicy) -> str:
    return hashlib.sha256(_canonical_json_bytes(policy.to_dict())).hexdigest()


def label_rank(label: ConfidenceLabel) -> int | None:
    return _LABEL_RANK.get(label)


def worse_label(a: ConfidenceLabel, b: ConfidenceLabel) -> ConfidenceLabel:
    """Return the weaker of two present labels (NOT_AVAILABLE not allowed)."""
    if a == "NOT_AVAILABLE" or b == "NOT_AVAILABLE":
        raise ValueError("NOT_AVAILABLE cannot participate in worse_label")
    return a if _LABEL_RANK[a] <= _LABEL_RANK[b] else b


def label_from_count(
    value: Decimal | int | None,
    floors: ConfidenceDimensionFloors,
) -> ConfidenceLabel:
    """Map a non-negative count/ratio onto a label using policy floors."""
    if value is None:
        return "NOT_AVAILABLE"
    measured = Decimal(str(value))
    low = Decimal(floors.low_floor)
    medium = Decimal(floors.medium_floor)
    high = Decimal(floors.high_floor)
    if measured < low:
        return "INSUFFICIENT"
    if measured < medium:
        return "LOW"
    if measured < high:
        return "MEDIUM"
    return "HIGH"


_POLICY_1_0 = ConfidencePolicy(
    version="1.0",
    description=(
        "Generic P4.9 evidence-confidence floors (#288). Public example defaults "
        "aligned with gate policy sample floor (min_closed_trades=10). Not private "
        "Strategy V1 / P5 thresholds. HIGH requires trade_sample, time_coverage, "
        "bootstrap_uncertainty present plus documented multiple_testing metadata. "
        "bootstrap_uncertainty measures floor(series_length/block_length). "
        "PSR/DSR/PBO/MTRL and symbol/concentration/effective-n deferred (#345)."
    ),
    dimensions=(
        ConfidenceDimensionFloors(
            name="trade_sample",
            description="Closed trades from sealed metrics.json.",
            low_floor="10",
            medium_floor="30",
            high_floor="100",
            required=True,
        ),
        ConfidenceDimensionFloors(
            name="time_coverage",
            description=(
                "Equity period count (len(equity)-1) as a time-length proxy "
                "(not a claim of independent segments; see #345)."
            ),
            low_floor="10",
            medium_floor="60",
            high_floor="252",
            required=False,
        ),
        ConfidenceDimensionFloors(
            name="oos_folds",
            description="Complete walk-forward folds from sealed robustness manifest.",
            low_floor="2",
            medium_floor="3",
            high_floor="5",
            required=False,
        ),
        ConfidenceDimensionFloors(
            name="parameter_plateau",
            description="Complete parameter-stability neighbors (excluding frozen).",
            low_floor="3",
            medium_floor="5",
            high_floor="8",
            required=False,
        ),
        ConfidenceDimensionFloors(
            name="bootstrap_uncertainty",
            description=(
                "Effective block count floor(series_length / block_length) from "
                "block bootstrap (serial-dependence-aware proxy)."
            ),
            low_floor="2",
            medium_floor="20",
            high_floor="60",
            required=False,
        ),
        ConfidenceDimensionFloors(
            name="regime_coverage",
            description="Trade→regime assignment coverage ratio (0–1).",
            low_floor="0.80",
            medium_floor="0.90",
            high_floor="0.95",
            required=False,
        ),
    ),
    high_requires_dimensions=(
        "trade_sample",
        "time_coverage",
        "bootstrap_uncertainty",
    ),
    high_requires_limitations_documented=("multiple_testing",),
    high_cap_label="MEDIUM",
)

_POLICY_REGISTRY: dict[str, ConfidencePolicy] = {"1.0": _POLICY_1_0}

# Frozen content hash of confidence policy 1.0 (review-pinned literal).
# Recompute via compute_confidence_policy_content_hash(get_confidence_policy("1.0"))
# if policy 1.0 content changes before merge; never silently edit after publish.
CONFIDENCE_POLICY_1_0_CONTENT_HASH = (
    "22748e176aa64ed36e01ac1911ac73b2314cb9ad22612b2206f80faec190d706"
)


def get_confidence_policy(version: str) -> ConfidencePolicy:
    try:
        return _POLICY_REGISTRY[version]
    except KeyError as exc:
        msg = f"unknown confidence policy version: {version!r}"
        raise ConfidencePolicyError(msg) from exc


def list_confidence_policy_versions() -> tuple[str, ...]:
    return tuple(sorted(_POLICY_REGISTRY))


def verify_confidence_policy_content_hash(version: str, expected: str) -> None:
    policy = get_confidence_policy(version)
    actual = compute_confidence_policy_content_hash(policy)
    if actual != expected:
        msg = (
            f"confidence policy content hash mismatch for version {version!r}: "
            f"persisted={expected!r} current={actual!r}"
        )
        raise ConfidencePolicyError(msg)
