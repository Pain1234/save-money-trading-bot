"""Per-regime raw metric computation from attributed trades/equity (#287)."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any

from research.metrics_contract import compute_gross_pnl
from research.regime_quality.availability import NOT_AVAILABLE
from research.regime_quality.join import trade_cost_components, trade_notional


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
    downside_deviation: Decimal | None
    tail_loss: Decimal | None
    subperiod_stability: Decimal | None
    win_rate: Decimal | None
    expectancy: Decimal | None
    profit_factor: Decimal | None
    largest_losing_streak: int | None
    pnl_concentration: Decimal | None
    time_in_market: Decimal | None
    exposure: Decimal | None
    turnover: Decimal | None
    symbol_net_pnl: dict[str, Decimal]
    benchmark_delta: str | None
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
            "downside_deviation": _dec_str(self.downside_deviation)
            if self.downside_deviation is not None
            else NOT_AVAILABLE,
            "tail_loss": _dec_str(self.tail_loss)
            if self.tail_loss is not None
            else NOT_AVAILABLE,
            "subperiod_stability": _dec_str(self.subperiod_stability)
            if self.subperiod_stability is not None
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


def _contiguous_episodes(
    timeline: Sequence[tuple[date, str | None, Mapping[str, Any]]],
    cell_id: str,
) -> list[list[Mapping[str, Any]]]:
    """Split chronological timeline into contiguous runs of ``cell_id``."""
    episodes: list[list[Mapping[str, Any]]] = []
    current: list[Mapping[str, Any]] = []
    for _day, tagged_cell, snap in timeline:
        if tagged_cell == cell_id:
            current.append(snap)
        elif current:
            episodes.append(current)
            current = []
    if current:
        episodes.append(current)
    return episodes


def max_drawdown_from_episodes(
    timeline: Sequence[tuple[date, str | None, Mapping[str, Any]]],
    cell_id: str,
) -> Decimal | None:
    """Max DD within contiguous regime episodes on a rebased return curve.

    Cross-regime equity gaps (e.g. BEAR losses between two BULL months) must
    not inflate the BULL drawdown. Each episode rebases to 1.0 and uses only
    intra-episode equity increments.
    """
    episodes = _contiguous_episodes(timeline, cell_id)
    max_dd: Decimal | None = None
    for episode in episodes:
        if len(episode) < 2:
            continue
        # Rebased equity path from intra-episode returns.
        level = Decimal("1")
        peak = level
        episode_dd = Decimal("0")
        prev = Decimal(str(episode[0]["equity"]))
        if prev <= 0:
            continue
        for snap in episode[1:]:
            cur = Decimal(str(snap["equity"]))
            if prev <= 0:
                prev = cur
                continue
            ret = cur / prev - Decimal("1")
            level = level * (Decimal("1") + ret)
            peak = max(peak, level)
            if peak > 0:
                dd = (peak - level) / peak
                if dd > episode_dd:
                    episode_dd = dd
            prev = cur
        if max_dd is None or episode_dd > max_dd:
            max_dd = episode_dd
    return max_dd


def _episode_returns(
    timeline: Sequence[tuple[date, str | None, Mapping[str, Any]]],
    cell_id: str,
) -> list[Decimal]:
    returns: list[Decimal] = []
    for episode in _contiguous_episodes(timeline, cell_id):
        if len(episode) < 2:
            continue
        prev = Decimal(str(episode[0]["equity"]))
        for snap in episode[1:]:
            cur = Decimal(str(snap["equity"]))
            if prev > 0:
                returns.append(cur / prev - Decimal("1"))
            prev = cur
    return returns


def _downside_deviation(returns: Sequence[Decimal]) -> Decimal | None:
    if len(returns) < 2:
        return None
    downs = [r for r in returns if r < 0]
    if not downs:
        return Decimal("0")
    mean = sum(downs, Decimal("0")) / Decimal(len(downs))
    var = sum((r - mean) ** 2 for r in downs) / Decimal(len(downs))
    return var.sqrt()


def _tail_loss(returns: Sequence[Decimal]) -> Decimal | None:
    """Worst single-period return within regime episodes (loss as positive)."""
    if not returns:
        return None
    worst = min(returns)
    if worst >= 0:
        return Decimal("0")
    return abs(worst)


def _subperiod_stability(returns: Sequence[Decimal]) -> Decimal | None:
    """1 - |mean_first_half - mean_second_half| / (1 + mean_abs); None if tiny."""
    if len(returns) < 4:
        return None
    mid = len(returns) // 2
    first = returns[:mid]
    second = returns[mid:]
    m1 = sum(first, Decimal("0")) / Decimal(len(first))
    m2 = sum(second, Decimal("0")) / Decimal(len(second))
    scale = Decimal("1") + (
        abs(m1) + abs(m2)
    ) / Decimal("2")
    return max(Decimal("0"), Decimal("1") - abs(m1 - m2) / scale)


def _time_in_market(equity: Sequence[Mapping[str, Any]]) -> Decimal | None:
    if not equity:
        return None
    open_days = sum(1 for row in equity if int(row.get("open_positions") or 0) > 0)
    return Decimal(open_days) / Decimal(len(equity))


def compute_benchmark_delta(
    *,
    cell_id: str,
    timeline: Sequence[tuple[date, str | None, Mapping[str, Any]]],
    trades: Sequence[Mapping[str, Any]],
    benchmark_closes: Mapping[date, Decimal] | None,
) -> str | None:
    """Strategy net return in cell minus buy-and-hold on labeled days.

    Returns Decimal string or None → caller maps to NOT_AVAILABLE.
    """
    if not benchmark_closes:
        return None
    days = sorted({d for d, cell, _ in timeline if cell == cell_id})
    if len(days) < 2:
        return None
    first_day, last_day = days[0], days[-1]
    first_px = benchmark_closes.get(first_day)
    last_px = benchmark_closes.get(last_day)
    if first_px is None or last_px is None or first_px <= 0:
        return None
    bh = last_px / first_px - Decimal("1")
    net = sum(
        (Decimal(str(t["net_pnl"])) for t in trades if t.get("net_pnl") is not None),
        Decimal("0"),
    )
    # Normalize strategy net by starting equity of first episode point if present.
    episode_points = [
        snap for d, cell, snap in timeline if cell == cell_id
    ]
    if not episode_points:
        return None
    start_eq = Decimal(str(episode_points[0]["equity"]))
    if start_eq <= 0:
        return None
    # Approximate: use first equity as capital base for the cell window.
    strat_ret = net / start_eq
    return format(strat_ret - bh, "f")


def compute_slice_metrics(
    *,
    cell_id: str,
    trades: Sequence[Mapping[str, Any]],
    equity: Sequence[Mapping[str, Any]],
    timeline: Sequence[tuple[date, str | None, Mapping[str, Any]]] = (),
    benchmark_closes: Mapping[date, Decimal] | None = None,
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
            downside_deviation=None,
            tail_loss=None,
            subperiod_stability=None,
            win_rate=None,
            expectancy=None,
            profit_factor=None,
            largest_losing_streak=0,
            pnl_concentration=None,
            time_in_market=None,
            exposure=None,
            turnover=None,
            symbol_net_pnl={},
            benchmark_delta=None,
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
    gross_profit = sum((Decimal(str(t["net_pnl"])) for t in winners), Decimal("0"))
    gross_loss = abs(sum((Decimal(str(t["net_pnl"])) for t in losers), Decimal("0")))
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

    notionals = [n for n in (trade_notional(t) for t in closed) if n is not None]
    turnover = sum(notionals, Decimal("0")) if notionals else None

    returns = _episode_returns(timeline, cell_id) if timeline else []
    max_dd = (
        max_drawdown_from_episodes(timeline, cell_id) if timeline else None
    )
    tim = _time_in_market(equity)
    exposure = tim
    bench = compute_benchmark_delta(
        cell_id=cell_id,
        timeline=timeline,
        trades=closed,
        benchmark_closes=benchmark_closes,
    )

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
        max_drawdown=max_dd,
        downside_deviation=_downside_deviation(returns),
        tail_loss=_tail_loss(returns),
        subperiod_stability=_subperiod_stability(returns),
        win_rate=win_rate,
        expectancy=expectancy,
        profit_factor=profit_factor,
        largest_losing_streak=streak,
        pnl_concentration=concentration,
        time_in_market=tim,
        exposure=exposure,
        turnover=turnover,
        symbol_net_pnl=dict(by_symbol),
        benchmark_delta=bench,
        status="ZERO_ACTIVITY" if zero else "OK",
    )
