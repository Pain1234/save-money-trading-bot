"""Join trades / equity points to ex-post regime day labels (#287).

Attribution rule (frozen for quality v1.0):
- Closed trades → ``exit_time`` calendar date (UTC date)
- Equity snapshots → ``time`` calendar date (UTC date)
- Days with ``status != OK`` or missing labels → excluded from regime cells;
  reported under ``insufficient_or_unlabeled`` counts.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any


@dataclass(frozen=True)
class DayRegimeKey:
    as_of: date
    period_id: str
    trend: str
    vol: str
    status: str

    @property
    def cell_id(self) -> str:
        return f"{self.trend}|{self.vol}"


def _as_utc_date(value: datetime | date | str) -> date:
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        ts = value if value.tzinfo is not None else value.replace(tzinfo=UTC)
        return ts.astimezone(UTC).date()
    # ISO string
    text = str(value)
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC).date()


def index_day_labels(
    regime_labels: Mapping[str, Any],
) -> dict[date, DayRegimeKey]:
    """Build as_of → DayRegimeKey from ``regime_labels.json`` payload."""
    raw = regime_labels.get("day_labels") or []
    out: dict[date, DayRegimeKey] = {}
    if not isinstance(raw, list):
        return out
    for row in raw:
        if not isinstance(row, dict):
            continue
        as_of = _as_utc_date(str(row["as_of"]))
        out[as_of] = DayRegimeKey(
            as_of=as_of,
            period_id=str(row.get("period_id") or ""),
            trend=str(row.get("trend") or "INSUFFICIENT"),
            vol=str(row.get("vol") or "INSUFFICIENT"),
            status=str(row.get("status") or "INSUFFICIENT"),
        )
    return out


def attribute_trades(
    trades: Sequence[Mapping[str, Any]],
    day_index: Mapping[date, DayRegimeKey],
) -> dict[str, list[dict[str, Any]]]:
    """Group trade dicts by regime cell_id; skip unlabeled/INSUFFICIENT days."""
    buckets: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for trade in trades:
        exit_raw = trade.get("exit_time")
        if exit_raw is None:
            continue
        day = _as_utc_date(exit_raw)
        key = day_index.get(day)
        if key is None or key.status != "OK":
            continue
        buckets[key.cell_id].append(dict(trade))
    return dict(buckets)


def attribute_equity(
    equity: Sequence[Mapping[str, Any]],
    day_index: Mapping[date, DayRegimeKey],
) -> dict[str, list[dict[str, Any]]]:
    """Group equity snapshots by regime cell_id."""
    buckets: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for snap in equity:
        t = snap.get("time")
        if t is None:
            continue
        day = _as_utc_date(t)
        key = day_index.get(day)
        if key is None or key.status != "OK":
            continue
        buckets[key.cell_id].append(dict(snap))
    return dict(buckets)


def _d(value: object | None, default: str = "0") -> Decimal:
    if value is None:
        return Decimal(default)
    return Decimal(str(value))


def trade_cost_components(trade: Mapping[str, Any]) -> tuple[Decimal, Decimal, Decimal]:
    return (
        _d(trade.get("fees")),
        _d(trade.get("slippage_cost")),
        _d(trade.get("funding")),
    )
