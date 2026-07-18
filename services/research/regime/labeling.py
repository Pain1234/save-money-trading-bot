"""Deterministic monthly regime labeling without look-ahead (Issue #285).

Each calendar month is labeled using **only** closes inside that month.
Day-level labels inherit the month's trend/vol. Volatility thresholds are
frozen on the classifier definition (never fitted from the evaluation window),
so future months cannot change past labels.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal

from research.regime.classifier import RegimeClassifier
from research.regime.taxonomy import TrendLabel, VolLabel


@dataclass(frozen=True)
class PriceBar:
    """Minimal daily close bar for regime classification."""

    as_of: date
    close: Decimal


@dataclass(frozen=True)
class PeriodLabel:
    """One calendar-month regime label."""

    period_id: str  # YYYY-MM
    trend: TrendLabel
    vol: VolLabel
    bar_count: int
    period_return: str | None
    realized_vol: str | None
    status: str  # OK | INSUFFICIENT


@dataclass(frozen=True)
class DayLabel:
    """Day inherits its calendar month's trend/vol (no intra-month look-ahead)."""

    as_of: date
    period_id: str
    trend: TrendLabel
    vol: VolLabel
    status: str


def bars_from_closes(
    closes: Sequence[tuple[date | datetime, Decimal | str | int | float]],
) -> tuple[PriceBar, ...]:
    """Normalize (timestamp, close) pairs into sorted unique daily bars."""
    by_day: dict[date, Decimal] = {}
    for ts, close in closes:
        day = ts.date() if isinstance(ts, datetime) else ts
        by_day[day] = Decimal(str(close))
    return tuple(
        PriceBar(as_of=day, close=by_day[day]) for day in sorted(by_day)
    )


def _period_id(day: date) -> str:
    return f"{day.year:04d}-{day.month:02d}"


def _population_stdev(values: Sequence[Decimal]) -> Decimal | None:
    n = len(values)
    if n < 2:
        return None
    mean = sum(values, Decimal("0")) / Decimal(n)
    var = sum((v - mean) ** 2 for v in values) / Decimal(n)
    return var.sqrt()


def _classify_trend(
    period_return: Decimal, classifier: RegimeClassifier
) -> TrendLabel:
    bull = Decimal(classifier.trend_bull_min)
    bear = Decimal(classifier.trend_bear_max)
    if period_return >= bull:
        return "BULL"
    if period_return <= bear:
        return "BEAR"
    return "SIDEWAYS"


def _classify_vol(
    realized_vol: Decimal, classifier: RegimeClassifier
) -> VolLabel:
    low_max = Decimal(classifier.vol_low_max)
    high_min = Decimal(classifier.vol_high_min)
    if realized_vol < low_max:
        return "LOW_VOL"
    if realized_vol >= high_min:
        return "HIGH_VOL"
    return "NORMAL_VOL"


def _label_period(
    period_id: str,
    bars: Sequence[PriceBar],
    classifier: RegimeClassifier,
) -> PeriodLabel:
    if len(bars) < classifier.min_bars_per_period:
        return PeriodLabel(
            period_id=period_id,
            trend="INSUFFICIENT",
            vol="INSUFFICIENT",
            bar_count=len(bars),
            period_return=None,
            realized_vol=None,
            status="INSUFFICIENT",
        )

    first = bars[0].close
    last = bars[-1].close
    if first == 0:
        return PeriodLabel(
            period_id=period_id,
            trend="INSUFFICIENT",
            vol="INSUFFICIENT",
            bar_count=len(bars),
            period_return=None,
            realized_vol=None,
            status="INSUFFICIENT",
        )

    period_return = last / first - Decimal("1")
    daily_returns: list[Decimal] = []
    for prev, cur in zip(bars, bars[1:], strict=False):
        if prev.close == 0:
            continue
        daily_returns.append(cur.close / prev.close - Decimal("1"))

    realized = _population_stdev(daily_returns)
    if realized is None:
        return PeriodLabel(
            period_id=period_id,
            trend="INSUFFICIENT",
            vol="INSUFFICIENT",
            bar_count=len(bars),
            period_return=format(period_return, "f"),
            realized_vol=None,
            status="INSUFFICIENT",
        )

    return PeriodLabel(
        period_id=period_id,
        trend=_classify_trend(period_return, classifier),
        vol=_classify_vol(realized, classifier),
        bar_count=len(bars),
        period_return=format(period_return, "f"),
        realized_vol=format(realized, "f"),
        status="OK",
    )


def label_periods(
    bars: Sequence[PriceBar],
    classifier: RegimeClassifier,
) -> tuple[PeriodLabel, ...]:
    """Label each calendar month present in ``bars`` (deterministic order)."""
    if not bars:
        return ()

    grouped: dict[str, list[PriceBar]] = defaultdict(list)
    for bar in bars:
        grouped[_period_id(bar.as_of)].append(bar)

    period_ids = sorted(grouped)
    return tuple(
        _label_period(pid, tuple(grouped[pid]), classifier) for pid in period_ids
    )


def label_days(
    bars: Sequence[PriceBar],
    period_labels: Sequence[PeriodLabel],
) -> tuple[DayLabel, ...]:
    """Attach each bar to its month's trend/vol label."""
    by_period = {p.period_id: p for p in period_labels}
    out: list[DayLabel] = []
    for bar in bars:
        pid = _period_id(bar.as_of)
        period = by_period[pid]
        out.append(
            DayLabel(
                as_of=bar.as_of,
                period_id=pid,
                trend=period.trend,
                vol=period.vol,
                status=period.status,
            )
        )
    return tuple(out)


def regime_distribution(
    period_labels: Sequence[PeriodLabel],
) -> dict[str, dict[str, int]]:
    """Count OK periods by trend and vol (INSUFFICIENT tracked separately)."""
    trend_counts: dict[str, int] = defaultdict(int)
    vol_counts: dict[str, int] = defaultdict(int)
    status_counts: dict[str, int] = defaultdict(int)
    for period in period_labels:
        status_counts[period.status] += 1
        trend_counts[period.trend] += 1
        vol_counts[period.vol] += 1
    return {
        "trend": dict(sorted(trend_counts.items())),
        "vol": dict(sorted(vol_counts.items())),
        "status": dict(sorted(status_counts.items())),
    }
