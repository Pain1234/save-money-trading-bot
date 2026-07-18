"""Regime label artifact build / seal helpers (Issue #285).

Produces ``regime_labels.json`` (+ companion ``.sha256``) suitable for later
scorecard assembly (#291). Does **not** create a second ExperimentRegistry —
callers may store under ``artifacts/research/regimes/{classification_id}/``.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

from research.regime.classifier import (
    RegimeClassifier,
    compute_classifier_content_hash,
)
from research.regime.labeling import (
    LABELING_MODE,
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
    detect_calendar_gaps,
    detect_period_transitions,
    label_day_events,
)

REGIME_LABELS_SCHEMA_VERSION = "1.0"
REGIME_LABELS_FILENAME = "regime_labels.json"


class RegimeArtifactError(Exception):
    """Empty input, seal mismatch, or path errors."""


def _canonical_json_bytes(payload: object) -> bytes:
    return json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def compute_bars_content_hash(bars: Sequence[PriceBar]) -> str:
    payload = [
        {"as_of": b.as_of.isoformat(), "close": format(b.close, "f")}
        for b in bars
    ]
    return hashlib.sha256(_canonical_json_bytes(payload)).hexdigest()


def compute_classification_id(
    *,
    classifier_version: str,
    classifier_content_hash: str,
    dataset_id: str,
    dataset_content_hash: str,
    reference_symbol: str,
    bars_content_hash: str,
) -> str:
    """Deterministic id: same pins + bars → same classification_id."""
    digest = hashlib.sha256(
        _canonical_json_bytes(
            {
                "bars_content_hash": bars_content_hash,
                "classifier_content_hash": classifier_content_hash,
                "classifier_version": classifier_version,
                "dataset_content_hash": dataset_content_hash,
                "dataset_id": dataset_id,
                "reference_symbol": reference_symbol,
            }
        )
    ).hexdigest()
    return f"clf_{digest}"


@dataclass(frozen=True)
class RegimeClassificationResult:
    """In-memory classification output before persistence."""

    artifact: dict[str, object]
    classification_id: str
    period_labels: tuple[PeriodLabel, ...]
    day_labels: tuple[DayLabel, ...]
    transitions: tuple[PeriodTransition, ...]
    day_events: tuple[DayEventLabel, ...]


def classify_regime_series(
    *,
    classifier: RegimeClassifier,
    bars: Sequence[PriceBar],
    dataset_id: str,
    dataset_content_hash: str,
    reference_symbol: str,
) -> RegimeClassificationResult:
    """Run deterministic labeling + transitions; fail closed on empty series."""
    if not bars:
        raise RegimeArtifactError(
            "empty price series: fail-closed (no regime labels)"
        )

    ordered = tuple(sorted(bars, key=lambda b: b.as_of))
    clf_hash = compute_classifier_content_hash(classifier)
    bars_hash = compute_bars_content_hash(ordered)
    classification_id = compute_classification_id(
        classifier_version=classifier.version,
        classifier_content_hash=clf_hash,
        dataset_id=dataset_id,
        dataset_content_hash=dataset_content_hash,
        reference_symbol=reference_symbol,
        bars_content_hash=bars_hash,
    )

    periods = label_periods(ordered, classifier)
    days = label_days(ordered, periods)
    adjacency = classifier.require_calendar_adjacency
    transitions = detect_period_transitions(
        periods, require_calendar_adjacency=adjacency
    )
    gaps = detect_calendar_gaps(periods)
    events = label_day_events(
        ordered,
        days,
        periods,
        classifier,
        require_calendar_adjacency=adjacency,
    )

    artifact: dict[str, object] = {
        "schema_version": REGIME_LABELS_SCHEMA_VERSION,
        "classification_id": classification_id,
        "classifier_version": classifier.version,
        "classifier_content_hash": clf_hash,
        "labeling_mode": classifier.labeling_mode or LABELING_MODE,
        "point_in_time_safe": classifier.point_in_time_safe,
        "usage": {
            "allowed": [
                "ex_post_attribution",
                "regime_quality_breakdown",
                "scorecard_layer_2",
            ],
            "forbidden": [
                "point_in_time_signal",
                "live_entry_filter",
                "causal_intrabar_decision",
            ],
        },
        "dataset_id": dataset_id,
        "dataset_content_hash": dataset_content_hash,
        "reference_symbol": reference_symbol,
        "bars_content_hash": bars_hash,
        "bar_count": len(ordered),
        "period_labels": [
            {
                "period_id": p.period_id,
                "trend": p.trend,
                "vol": p.vol,
                "bar_count": p.bar_count,
                "period_return": p.period_return,
                "realized_vol": p.realized_vol,
                "status": p.status,
            }
            for p in periods
        ],
        "day_labels": [
            {
                "as_of": d.as_of.isoformat(),
                "period_id": d.period_id,
                "trend": d.trend,
                "vol": d.vol,
                "status": d.status,
                "attribution": "period_ex_post",
            }
            for d in days
        ],
        "transitions": [
            {
                "from_period_id": t.from_period_id,
                "to_period_id": t.to_period_id,
                "from_trend": t.from_trend,
                "to_trend": t.to_trend,
                "from_vol": t.from_vol,
                "to_vol": t.to_vol,
                "transition_id": t.transition_id,
                "trend_changed": t.trend_changed,
                "vol_changed": t.vol_changed,
            }
            for t in transitions
        ],
        "calendar_gaps": [
            {
                "after_period_id": g.after_period_id,
                "before_period_id": g.before_period_id,
                "missing_period_ids": list(g.missing_period_ids),
            }
            for g in gaps
        ],
        "day_events": [
            {
                "as_of": e.as_of.isoformat(),
                "period_id": e.period_id,
                "event": e.event,
                "transition_id": e.transition_id,
                "attribution": "period_ex_post",
            }
            for e in events
        ],
        "distribution": regime_distribution(periods),
    }
    return RegimeClassificationResult(
        artifact=artifact,
        classification_id=classification_id,
        period_labels=periods,
        day_labels=days,
        transitions=transitions,
        day_events=events,
    )


def classify_closes(
    *,
    classifier: RegimeClassifier,
    closes: Sequence[tuple[date | datetime, Decimal | str | int | float]],
    dataset_id: str,
    dataset_content_hash: str,
    reference_symbol: str,
) -> RegimeClassificationResult:
    """Convenience wrapper accepting raw (timestamp, close) pairs."""
    return classify_regime_series(
        classifier=classifier,
        bars=bars_from_closes(closes),
        dataset_id=dataset_id,
        dataset_content_hash=dataset_content_hash,
        reference_symbol=reference_symbol,
    )


def write_regime_labels_artifact(
    directory: Path, artifact: dict[str, object]
) -> Path:
    """Atomic-ish write of regime_labels.json + .sha256 seal companion."""
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / REGIME_LABELS_FILENAME
    if target.exists():
        raise RegimeArtifactError(
            f"refusing to overwrite existing regime labels: {target}"
        )
    payload = _canonical_json_bytes(artifact)
    digest = hashlib.sha256(payload).hexdigest()
    tmp = directory / f".{REGIME_LABELS_FILENAME}.tmp"
    tmp.write_bytes(payload)
    tmp.replace(target)
    (directory / f"{REGIME_LABELS_FILENAME}.sha256").write_text(
        f"{digest}  {REGIME_LABELS_FILENAME}\n", encoding="utf-8"
    )
    return target


def verify_regime_labels_seal(directory: Path) -> str:
    """Fail closed if regime_labels.json does not match its .sha256 seal."""
    target = directory / REGIME_LABELS_FILENAME
    seal = directory / f"{REGIME_LABELS_FILENAME}.sha256"
    if not target.is_file() or not seal.is_file():
        raise RegimeArtifactError(
            f"missing regime labels artifact or seal under {directory}"
        )
    expected = seal.read_text(encoding="utf-8").split()[0]
    actual = hashlib.sha256(target.read_bytes()).hexdigest()
    if actual != expected:
        raise RegimeArtifactError(
            f"regime labels seal mismatch: expected {expected}, got {actual}"
        )
    return actual
