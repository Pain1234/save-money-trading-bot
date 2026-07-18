"""Join trades / equity points to ex-post regime day labels (#287).

Attribution rule (frozen for quality v1.0):
- Closed trades → ``exit_time`` calendar date (UTC date)
- Equity snapshots → ``time`` calendar date (UTC date)

Trades on missing or ``INSUFFICIENT`` days are **not** silently dropped from
reconciliation: they are counted under unlabeled / insufficient buckets with
their PnL preserved for coverage reporting.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
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


@dataclass
class TradeAttribution:
    """Full trade attribution with reconciliation counters."""

    by_cell: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    unlabeled: list[dict[str, Any]] = field(default_factory=list)
    insufficient: list[dict[str, Any]] = field(default_factory=list)
    open_or_missing_exit: list[dict[str, Any]] = field(default_factory=list)

    @property
    def closed_total(self) -> int:
        return (
            sum(len(v) for v in self.by_cell.values())
            + len(self.unlabeled)
            + len(self.insufficient)
        )

    @property
    def closed_labeled(self) -> int:
        return sum(len(v) for v in self.by_cell.values())

    def source_net_pnl(self) -> Decimal:
        total = Decimal("0")
        for group in (
            *self.by_cell.values(),
            self.unlabeled,
            self.insufficient,
        ):
            for trade in group:
                if trade.get("net_pnl") is not None:
                    total += Decimal(str(trade["net_pnl"]))
        return total

    def excluded_net_pnl(self) -> Decimal:
        total = Decimal("0")
        for trade in (*self.unlabeled, *self.insufficient):
            if trade.get("net_pnl") is not None:
                total += Decimal(str(trade["net_pnl"]))
        return total

    def attributed_net_pnl(self) -> Decimal:
        total = Decimal("0")
        for group in self.by_cell.values():
            for trade in group:
                if trade.get("net_pnl") is not None:
                    total += Decimal(str(trade["net_pnl"]))
        return total


@dataclass
class EquityAttribution:
    by_cell: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    # Full timeline tagged for episode-aware drawdown (chronological).
    timeline: list[tuple[date, str | None, dict[str, Any]]] = field(
        default_factory=list
    )
    unlabeled_points: int = 0
    insufficient_points: int = 0


def _as_utc_date(value: datetime | date | str) -> date:
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        ts = value if value.tzinfo is not None else value.replace(tzinfo=UTC)
        return ts.astimezone(UTC).date()
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
) -> TradeAttribution:
    """Attribute closed trades; preserve unlabeled/insufficient for reconciliation."""
    result = TradeAttribution()
    buckets: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for trade in trades:
        exit_raw = trade.get("exit_time")
        if exit_raw is None:
            result.open_or_missing_exit.append(dict(trade))
            continue
        day = _as_utc_date(exit_raw)
        key = day_index.get(day)
        row = dict(trade)
        if key is None:
            result.unlabeled.append(row)
            continue
        if key.status != "OK":
            result.insufficient.append(row)
            continue
        buckets[key.cell_id].append(row)
    result.by_cell = dict(buckets)
    return result


def attribute_equity(
    equity: Sequence[Mapping[str, Any]],
    day_index: Mapping[date, DayRegimeKey],
) -> EquityAttribution:
    """Attribute equity snapshots and build a chronological tagged timeline."""
    result = EquityAttribution()
    buckets: dict[str, list[dict[str, Any]]] = defaultdict(list)
    tagged: list[tuple[date, str | None, dict[str, Any]]] = []
    for snap in equity:
        t = snap.get("time")
        if t is None:
            continue
        day = _as_utc_date(t)
        row = dict(snap)
        key = day_index.get(day)
        if key is None:
            result.unlabeled_points += 1
            tagged.append((day, None, row))
            continue
        if key.status != "OK":
            result.insufficient_points += 1
            tagged.append((day, None, row))
            continue
        buckets[key.cell_id].append(row)
        tagged.append((day, key.cell_id, row))
    tagged.sort(key=lambda item: (item[0], str(item[2].get("time") or "")))
    result.by_cell = dict(buckets)
    result.timeline = tagged
    return result


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


def trade_notional(trade: Mapping[str, Any]) -> Decimal | None:
    """Notional from BacktestTrade fields (quantity × entry_fill_price)."""
    qty = trade.get("quantity")
    if qty is None:
        qty = trade.get("qty")  # legacy alias
    px = trade.get("entry_fill_price")
    if px is None:
        px = trade.get("entry_price")  # legacy alias
    if qty is None or px is None:
        return None
    return abs(Decimal(str(qty)) * Decimal(str(px)))
