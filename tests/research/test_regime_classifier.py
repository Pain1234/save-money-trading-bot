"""Unit tests for versioned regime / transition classifier (Issue #285 / P4.9)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from research.regime import (
    PriceBar,
    RegimeArtifactError,
    RegimeClassifierError,
    classify_closes,
    classify_regime_series,
    compute_classifier_content_hash,
    get_classifier,
    list_classifier_versions,
    verify_classifier_content_hash,
    verify_regime_labels_seal,
    write_regime_labels_artifact,
)
from research.regime.classifier import RegimeClassifier


def _month_closes(
    *,
    year: int,
    month: int,
    start: Decimal,
    daily_return: Decimal,
    days: int = 20,
) -> list[tuple[date, Decimal]]:
    closes: list[tuple[date, Decimal]] = []
    price = start
    for day in range(1, days + 1):
        closes.append((date(year, month, day), price))
        price = price * (Decimal("1") + daily_return)
    return closes


def test_known_classifier_version() -> None:
    clf = get_classifier("1.0")
    assert clf.version == "1.0"
    assert clf.min_bars_per_period >= 1


def test_unknown_classifier_version_raises() -> None:
    with pytest.raises(RegimeClassifierError):
        get_classifier("999.0")


def test_content_hash_deterministic() -> None:
    clf = get_classifier("1.0")
    a = compute_classifier_content_hash(clf)
    b = compute_classifier_content_hash(clf)
    assert a == b
    assert len(a) == 64
    int(a, 16)


def test_content_hash_changes_when_threshold_changes() -> None:
    clf = get_classifier("1.0")
    mutated = RegimeClassifier(
        version=clf.version,
        description=clf.description,
        trend_bull_min="0.99",
        trend_bear_max=clf.trend_bear_max,
        vol_low_max=clf.vol_low_max,
        vol_high_min=clf.vol_high_min,
        min_bars_per_period=clf.min_bars_per_period,
        transition_window_bars=clf.transition_window_bars,
    )
    assert compute_classifier_content_hash(clf) != compute_classifier_content_hash(
        mutated
    )


def test_verify_rejects_stale_hash() -> None:
    with pytest.raises(RegimeClassifierError, match="content hash mismatch"):
        verify_classifier_content_hash("1.0", "0" * 64)


def test_verify_detects_silent_edit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from research.regime import classifier as clf_mod

    original = get_classifier("1.0")
    persisted = compute_classifier_content_hash(original)
    edited = RegimeClassifier(
        version="1.0",
        description=original.description,
        trend_bull_min="0.99",
        trend_bear_max=original.trend_bear_max,
        vol_low_max=original.vol_low_max,
        vol_high_min=original.vol_high_min,
        min_bars_per_period=original.min_bars_per_period,
        transition_window_bars=original.transition_window_bars,
    )
    monkeypatch.setitem(clf_mod._CLASSIFIER_REGISTRY, "1.0", edited)
    with pytest.raises(RegimeClassifierError, match="content hash mismatch"):
        verify_classifier_content_hash("1.0", persisted)


def test_bull_month() -> None:
    result = classify_closes(
        classifier=get_classifier("1.0"),
        closes=_month_closes(
            year=2024, month=1, start=Decimal("100"), daily_return=Decimal("0.005")
        ),
        dataset_id="ds",
        dataset_content_hash="a" * 64,
        reference_symbol="BTC",
    )
    assert len(result.period_labels) == 1
    assert result.period_labels[0].status == "OK"
    assert result.period_labels[0].trend == "BULL"
    assert result.artifact["distribution"]["trend"]["BULL"] == 1


def test_bear_and_sideways() -> None:
    bear = classify_closes(
        classifier=get_classifier("1.0"),
        closes=_month_closes(
            year=2024, month=2, start=Decimal("100"), daily_return=Decimal("-0.005")
        ),
        dataset_id="ds",
        dataset_content_hash="a" * 64,
        reference_symbol="BTC",
    )
    sideways = classify_closes(
        classifier=get_classifier("1.0"),
        closes=_month_closes(
            year=2024, month=3, start=Decimal("100"), daily_return=Decimal("0.0001")
        ),
        dataset_id="ds",
        dataset_content_hash="a" * 64,
        reference_symbol="BTC",
    )
    assert bear.period_labels[0].trend == "BEAR"
    assert sideways.period_labels[0].trend == "SIDEWAYS"


def test_short_month_insufficient() -> None:
    closes = [(date(2024, 4, d), Decimal("100")) for d in range(1, 4)]
    result = classify_closes(
        classifier=get_classifier("1.0"),
        closes=closes,
        dataset_id="ds",
        dataset_content_hash="a" * 64,
        reference_symbol="BTC",
    )
    period = result.period_labels[0]
    assert period.status == "INSUFFICIENT"
    assert period.trend == "INSUFFICIENT"
    assert period.period_return is None


def test_idempotent_classification() -> None:
    closes = _month_closes(
        year=2024, month=5, start=Decimal("200"), daily_return=Decimal("0.006")
    )
    a = classify_closes(
        classifier=get_classifier("1.0"),
        closes=closes,
        dataset_id="ds",
        dataset_content_hash="b" * 64,
        reference_symbol="BTC",
    )
    b = classify_closes(
        classifier=get_classifier("1.0"),
        closes=closes,
        dataset_id="ds",
        dataset_content_hash="b" * 64,
        reference_symbol="BTC",
    )
    assert a.artifact == b.artifact
    assert a.classification_id == b.classification_id


def test_no_cross_month_lookahead_on_period_labels() -> None:
    """January period metrics must not use February closes."""
    jan = _month_closes(
        year=2024, month=1, start=Decimal("100"), daily_return=Decimal("0.005")
    )
    alone = classify_closes(
        classifier=get_classifier("1.0"),
        closes=jan,
        dataset_id="ds",
        dataset_content_hash="c" * 64,
        reference_symbol="BTC",
    )
    with_feb = classify_closes(
        classifier=get_classifier("1.0"),
        closes=[
            *jan,
            *_month_closes(
                year=2024, month=2, start=Decimal("50"), daily_return=Decimal("-0.01")
            ),
        ],
        dataset_id="ds",
        dataset_content_hash="c" * 64,
        reference_symbol="BTC",
    )
    jan_alone = alone.period_labels[0]
    jan_with = next(p for p in with_feb.period_labels if p.period_id == "2024-01")
    assert jan_alone.trend == jan_with.trend
    assert jan_alone.vol == jan_with.vol
    assert jan_alone.period_return == jan_with.period_return


def test_day_labels_are_ex_post_attribution_not_point_in_time() -> None:
    """Completing a month can change earlier days' inherited labels (by design)."""
    early = _month_closes(
        year=2024, month=1, start=Decimal("100"), daily_return=Decimal("0.0001"), days=10
    )
    partial = classify_closes(
        classifier=get_classifier("1.0"),
        closes=early,
        dataset_id="ds",
        dataset_content_hash="i" * 64,
        reference_symbol="BTC",
    )
    full = _month_closes(
        year=2024, month=1, start=Decimal("100"), daily_return=Decimal("0.006"), days=20
    )
    complete = classify_closes(
        classifier=get_classifier("1.0"),
        closes=full,
        dataset_id="ds",
        dataset_content_hash="i" * 64,
        reference_symbol="BTC",
    )
    day1_partial = next(d for d in partial.day_labels if d.as_of.day == 1)
    day1_complete = next(d for d in complete.day_labels if d.as_of.day == 1)
    assert day1_partial.trend == "SIDEWAYS"
    assert day1_complete.trend == "BULL"
    assert complete.artifact["point_in_time_safe"] is False
    assert complete.artifact["labeling_mode"] == "ex_post_period_attribution"
    assert "point_in_time_signal" in complete.artifact["usage"]["forbidden"]
    assert all(
        row["attribution"] == "period_ex_post"
        for row in complete.artifact["day_labels"]  # type: ignore[union-attr]
    )


def test_missing_month_does_not_fabricate_transition() -> None:
    """Jan + Mar without Feb must not emit Jan→Mar BULL_TO_BEAR."""
    closes = [
        *_month_closes(
            year=2024, month=1, start=Decimal("100"), daily_return=Decimal("0.006")
        ),
        *_month_closes(
            year=2024, month=3, start=Decimal("100"), daily_return=Decimal("-0.006")
        ),
    ]
    result = classify_closes(
        classifier=get_classifier("1.0"),
        closes=closes,
        dataset_id="ds",
        dataset_content_hash="j" * 64,
        reference_symbol="BTC",
    )
    assert result.transitions == ()
    assert result.artifact["calendar_gaps"] == [
        {
            "after_period_id": "2024-01",
            "before_period_id": "2024-03",
            "missing_period_ids": ["2024-02"],
        }
    ]
    assert all(
        e.event in ("STABLE_REGIME", "INSUFFICIENT") for e in result.day_events
    )


def test_transition_bull_to_bear() -> None:
    closes = [
        *_month_closes(
            year=2024, month=1, start=Decimal("100"), daily_return=Decimal("0.006")
        ),
        *_month_closes(
            year=2024, month=2, start=Decimal("100"), daily_return=Decimal("-0.006")
        ),
    ]
    result = classify_closes(
        classifier=get_classifier("1.0"),
        closes=closes,
        dataset_id="ds",
        dataset_content_hash="d" * 64,
        reference_symbol="BTC",
    )
    assert len(result.transitions) >= 1
    transition = result.transitions[0]
    assert transition.from_period_id == "2024-01"
    assert transition.to_period_id == "2024-02"
    assert transition.transition_id == "BULL_TO_BEAR"
    assert any(e.event == "TRANSITION_OUT" for e in result.day_events)
    assert any(e.event == "TRANSITION_IN" for e in result.day_events)


def test_high_vol_bucket() -> None:
    closes: list[tuple[date, Decimal]] = []
    price = Decimal("100")
    for day in range(1, 21):
        closes.append((date(2024, 8, day), price))
        price = price * (Decimal("1.10") if day % 2 == 1 else Decimal("0.91"))
    result = classify_closes(
        classifier=get_classifier("1.0"),
        closes=closes,
        dataset_id="ds",
        dataset_content_hash="e" * 64,
        reference_symbol="BTC",
    )
    assert result.period_labels[0].status == "OK"
    assert result.period_labels[0].vol == "HIGH_VOL"


def test_empty_series_fail_closed() -> None:
    with pytest.raises(RegimeArtifactError, match="empty price series"):
        classify_regime_series(
            classifier=get_classifier("1.0"),
            bars=(),
            dataset_id="ds",
            dataset_content_hash="f" * 64,
            reference_symbol="BTC",
        )


def test_artifact_seal_round_trip(tmp_path: Path) -> None:
    result = classify_closes(
        classifier=get_classifier("1.0"),
        closes=_month_closes(
            year=2024, month=9, start=Decimal("50"), daily_return=Decimal("0.004")
        ),
        dataset_id="ds-seal",
        dataset_content_hash="1" * 64,
        reference_symbol="BTC",
    )
    write_regime_labels_artifact(tmp_path, result.artifact)
    digest = verify_regime_labels_seal(tmp_path)
    assert len(digest) == 64
    payload = result.artifact
    assert payload["classifier_version"] == "1.0"
    assert payload["reference_symbol"] == "BTC"
    assert payload["point_in_time_safe"] is False
    assert payload["labeling_mode"] == "ex_post_period_attribution"
    assert "distribution" in payload
    assert "calendar_gaps" in payload


def test_list_versions_contains_1_0() -> None:
    assert "1.0" in list_classifier_versions()


def test_price_bar_path_matches_closes() -> None:
    bars = (
        PriceBar(as_of=date(2024, 10, 1), close=Decimal("100")),
        PriceBar(as_of=date(2024, 10, 2), close=Decimal("101")),
        PriceBar(as_of=date(2024, 10, 3), close=Decimal("102")),
        PriceBar(as_of=date(2024, 10, 4), close=Decimal("103")),
        PriceBar(as_of=date(2024, 10, 5), close=Decimal("104")),
    )
    result = classify_regime_series(
        classifier=get_classifier("1.0"),
        bars=bars,
        dataset_id="ds",
        dataset_content_hash="2" * 64,
        reference_symbol="BTC",
    )
    assert result.period_labels[0].period_id == "2024-10"
