"""Per-regime raw metric computation from attributed trades/equity (#287)."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from research.metrics_contract import compute_gross_pnl
from research.regime_quality.availability import NOT_AVAILABLE
from research.regime_quality.join import trade_cost_components


def _safe_div(num: Decimal, den: Decimal) -> Decimal | None:
    if den == 0:
        return None
    return num / den


def _dec_str(value: Decimal | None) -> str | None:
    if value is None:
        return None
    return format(value, "f")


@dataclass(frozen=True)
class RegimeSliceRaw:
    """Raw metrics for one regime cell (trend|vol)."""

    cell_id: str
    trend: str
    vol: str
    closed_trades: int
    zero_activity: bool
    net_pnl: Decimal
    gross_pnl: Decimal
    fees: Decimal
    slippage_costs: Decimal
    funding_costs: Decimal
    max_drawdown: Decimal | None
    win_rate: Decimal | None
    expectancy: Decimal | None
    profit_factor: Decimal | None
    largest_losing_streak: int | None
    pnl_concentration: Decimal | None
    time_in_market: Decimal | None
    exposure: Decimal | None
    turnover: Decimal | None
    symbol_net_pnl: dict[str, Decimal]
    benchmark_delta: str | None  # Decimal string or NOT_AVAILABLE
    status: str  # OK | ZERO_ACTIVITY | INSUFFICIENT_EVIDENCE

    def to_dict(self) -> dict[str, Any]:
        return {
            "cell_id": self.cell_id,
            "trend": self.trend,
            "vol": self.vol,
            "status": self.status,
            "zero_activity": self.zero_activity,
            "closed_trades": self.closed_trades,
            "net_pnl": _dec_str(self.net_pnl),
            "gross_pnl": _dec_str(self.gross_pnl),
            "costs": {
                "fees": _dec_str(self.fees),
                "slippage_costs": _dec_str(self.slippage_costs),
                "funding_costs": _dec_str(self.funding_costs),
            },
            "max_drawdown": _dec_str(self.max_drawdown)
            if self.max_drawdown is not None
            else NOT_AVAILABLE,
            "win_rate": _dec_str(self.win_rate)
            if self.win_rate is not None
            else NOT_AVAILABLE,
            "expectancy": _dec_str(self.expectancy)
            if self.expectancy is not None
            else NOT_AVAILABLE,
            "profit_factor": _dec_str(self.profit_factor)
            if self.profit_factor is not None
            else NOT_AVAILABLE,
            "largest_losing_streak": self.largest_losing_streak
            if self.largest_losing_streak is not None
            else NOT_AVAILABLE,
            "pnl_concentration": _dec_str(self.pnl_concentration)
            if self.pnl_concentration is not None
            else NOT_AVAILABLE,
            "time_in_market": _dec_str(self.time_in_market)
            if self.time_in_market is not None
            else NOT_AVAILABLE,
            "exposure": _dec_str(self.exposure)
            if self.exposure is not None
            else NOT_AVAILABLE,
            "turnover": _dec_str(self.turnover)
            if self.turnover is not None
            else NOT_AVAILABLE,
            "benchmark_delta": self.benchmark_delta
            if self.benchmark_delta is not None
            else NOT_AVAILABLE,
            "symbol_net_pnl": {
                sym: _dec_str(pnl) for sym, pnl in sorted(self.symbol_net_pnl.items())
            },
        }


def _largest_losing_streak(net_pnls: Sequence[Decimal]) -> int:
    best = 0
    cur = 0
    for pnl in net_pnls:
        if pnl < 0:
            cur += 1
            best = max(best, cur)
        else:
            cur = 0
    return best


def _max_drawdown_from_equity(equity: Sequence[Mapping[str, Any]]) -> Decimal | None:
    if len(equity) < 2:
        return None
    rows = sorted(equity, key=lambda r: str(r.get("time") or ""))
    peak = Decimal(str(rows[0]["equity"]))
    max_dd = Decimal("0")
    for row in rows:
        eq = Decimal(str(row["equity"]))
        peak = max(peak, eq)
        if peak > 0:
            dd = (peak - eq) / peak
            if dd > max_dd:
                max_dd = dd
    return max_dd


def _time_in_market(equity: Sequence[Mapping[str, Any]]) -> Decimal | None:
    if not equity:
        return None
    open_days = sum(
        1 for row in equity if int(row.get("open_positions") or 0) > 0
    )
    return Decimal(open_days) / Decimal(len(equity))


def compute_slice_metrics(
    *,
    cell_id: str,
    trades: Sequence[Mapping[str, Any]],
    equity: Sequence[Mapping[str, Any]],
    benchmark_delta: str | None = None,
) -> RegimeSliceRaw:
    trend, _, vol = cell_id.partition("|")
    closed = [t for t in trades if t.get("net_pnl") is not None]
    if not closed and not equity:
        return RegimeSliceRaw(
            cell_id=cell_id,
            trend=trend,
            vol=vol,
            closed_trades=0,
            zero_activity=True,
            net_pnl=Decimal("0"),
            gross_pnl=Decimal("0"),
            fees=Decimal("0"),
            slippage_costs=Decimal("0"),
            funding_costs=Decimal("0"),
            max_drawdown=None,
            win_rate=None,
            expectancy=None,
            profit_factor=None,
            largest_losing_streak=0,
            pnl_concentration=None,
            time_in_market=None,
            exposure=None,
            turnover=None,
            symbol_net_pnl={},
            benchmark_delta=benchmark_delta or NOT_AVAILABLE,
            status="ZERO_ACTIVITY",
        )

    net = sum((Decimal(str(t["net_pnl"])) for t in closed), Decimal("0"))
    fees = sum((trade_cost_components(t)[0] for t in closed), Decimal("0"))
    slip = sum((trade_cost_components(t)[1] for t in closed), Decimal("0"))
    fund = sum((trade_cost_components(t)[2] for t in closed), Decimal("0"))
    gross = compute_gross_pnl(net, fees, slip, fund)

    winners = [t for t in closed if Decimal(str(t["net_pnl"])) > 0]
    losers = [t for t in closed if Decimal(str(t["net_pnl"])) <= 0]
    trade_count = len(closed)
    win_rate = (
        _safe_div(Decimal(len(winners)), Decimal(trade_count)) if trade_count else None
    )
    expectancy = _safe_div(net, Decimal(trade_count)) if trade_count else None
    gross_profit = sum(
        (Decimal(str(t["net_pnl"])) for t in winners), Decimal("0")
    )
    gross_loss = abs(
        sum((Decimal(str(t["net_pnl"])) for t in losers), Decimal("0"))
    )
    profit_factor = _safe_div(gross_profit, gross_loss) if gross_loss > 0 else None

    pnls = [Decimal(str(t["net_pnl"])) for t in closed]
    streak = _largest_losing_streak(pnls) if pnls else 0
    if pnls:
        total_abs = sum((abs(p) for p in pnls), Decimal("0"))
        max_abs = max(abs(p) for p in pnls)
        concentration = _safe_div(max_abs, total_abs) if total_abs > 0 else None
    else:
        concentration = None

    by_symbol: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
    for t in closed:
        sym = str(t.get("symbol") or "UNKNOWN")
        by_symbol[sym] += Decimal(str(t["net_pnl"]))

    # Notional turnover proxy: sum |qty * entry_price| when present.
    turnover: Decimal | None = None
    notionals: list[Decimal] = []
    for t in closed:
        qty = t.get("qty")
        px = t.get("entry_price")
        if qty is not None and px is not None:
            notionals.append(abs(Decimal(str(qty)) * Decimal(str(px))))
    if notionals:
        turnover = sum(notionals, Decimal("0"))

    exposure = None  # requires position path; leave N/A unless equity open share used
    tim = _time_in_market(equity)
    if tim is not None:
        exposure = tim  # proxy: fraction of equity days with open positions

    zero = trade_count == 0
    return RegimeSliceRaw(
        cell_id=cell_id,
        trend=trend,
        vol=vol,
        closed_trades=trade_count,
        zero_activity=zero,
        net_pnl=net,
        gross_pnl=gross,
        fees=fees,
        slippage_costs=slip,
        funding_costs=fund,
        max_drawdown=_max_drawdown_from_equity(equity),
        win_rate=win_rate,
        expectancy=expectancy,
        profit_factor=profit_factor,
        largest_losing_streak=streak,
        pnl_concentration=concentration,
        time_in_market=tim,
        exposure=exposure,
        turnover=turnover,
        symbol_net_pnl=dict(by_symbol),
        benchmark_delta=benchmark_delta or NOT_AVAILABLE,
        status="ZERO_ACTIVITY" if zero else "OK",
    )
