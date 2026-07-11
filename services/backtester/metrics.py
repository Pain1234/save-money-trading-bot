"""Backtest metrics calculation."""

from __future__ import annotations

import math
from datetime import datetime
from decimal import Decimal

from strategy_engine.models import EntryType as ET

from backtester.models import (
    BacktestMetrics,
    BacktestTrade,
    DrawdownSnapshot,
    EntryTypeMetrics,
    EquitySnapshot,
    SymbolMetrics,
)


def _safe_div(num: Decimal, den: Decimal) -> Decimal | None:
    if den == 0:
        return None
    return num / den


def compute_drawdown_curve(curve: tuple[EquitySnapshot, ...]) -> tuple[DrawdownSnapshot, ...]:
    result: list[DrawdownSnapshot] = []
    peak = Decimal("0")
    for snap in curve:
        peak = max(peak, snap.equity)
        dd = _safe_div(peak - snap.equity, peak) or Decimal("0")
        result.append(
            DrawdownSnapshot(
                time=snap.time,
                equity=snap.equity,
                peak_equity=peak,
                drawdown_pct=dd,
            )
        )
    return tuple(result)


def _years_between(start: datetime, end: datetime) -> Decimal:
    days = Decimal(str((end - start).days))
    return days / Decimal("365.25")


def compute_metrics(
    *,
    trades: tuple[BacktestTrade, ...],
    equity_curve: tuple[EquitySnapshot, ...],
    start_capital: Decimal,
    end_capital: Decimal,
    total_fees: Decimal,
    total_funding: Decimal,
    total_slippage: Decimal,
    data_start: datetime | None,
    data_end: datetime | None,
) -> BacktestMetrics:
    closed = [t for t in trades if t.net_pnl is not None]
    trade_count = len(closed)
    winners = [t for t in closed if t.net_pnl is not None and t.net_pnl > 0]
    losers = [t for t in closed if t.net_pnl is not None and t.net_pnl <= 0]

    win_rate = _safe_div(Decimal(len(winners)), Decimal(trade_count)) if trade_count else None

    gross_profit = sum((t.net_pnl for t in winners if t.net_pnl), Decimal("0"))
    gross_loss = abs(sum((t.net_pnl for t in losers if t.net_pnl), Decimal("0")))
    profit_factor = _safe_div(gross_profit, gross_loss) if gross_loss > 0 else None

    net_pnls = [t.net_pnl for t in closed if t.net_pnl is not None]
    expectancy_usd = (
        _safe_div(sum(net_pnls, Decimal("0")), Decimal(trade_count)) if trade_count else None
    )

    r_vals = [t.r_multiple for t in closed if t.r_multiple is not None]
    expectancy_r = _safe_div(sum(r_vals, Decimal("0")), Decimal(len(r_vals))) if r_vals else None
    average_r = _safe_div(sum(r_vals, Decimal("0")), Decimal(len(r_vals))) if r_vals else None

    winner_pnl = sum((t.net_pnl for t in winners if t.net_pnl), Decimal("0"))
    loser_pnl = sum((t.net_pnl for t in losers if t.net_pnl), Decimal("0"))
    avg_winner = _safe_div(winner_pnl, Decimal(len(winners))) if winners else None
    avg_loser = _safe_div(loser_pnl, Decimal(len(losers))) if losers else None

    total_return = _safe_div(end_capital - start_capital, start_capital)
    cagr = None
    if (
        data_start
        and data_end
        and total_return is not None
        and end_capital > 0
        and start_capital > 0
    ):
        years = _years_between(data_start, data_end)
        if years > 0:
            try:
                tr_float = float(total_return + Decimal("1"))
                cagr_val = tr_float ** (1 / float(years)) - 1
                cagr = Decimal(str(cagr_val))
            except (OverflowError, ValueError, ZeroDivisionError):
                cagr = None

    dd_curve = compute_drawdown_curve(equity_curve)
    max_dd = max((d.drawdown_pct for d in dd_curve), default=Decimal("0"))

    returns: list[float] = []
    for i in range(1, len(equity_curve)):
        prev = equity_curve[i - 1].equity
        cur = equity_curve[i].equity
        if prev > 0:
            returns.append(float((cur - prev) / prev))

    sharpe = None
    sortino = None
    if len(returns) >= 2:
        mean_r = sum(returns) / len(returns)
        var = sum((r - mean_r) ** 2 for r in returns) / len(returns)
        std = math.sqrt(var) if var > 0 else 0.0
        if std > 0:
            sharpe = Decimal(str(mean_r / std * math.sqrt(252)))
        downside = [min(0.0, r) for r in returns]
        down_var = sum(d ** 2 for d in downside) / len(downside)
        down_std = math.sqrt(down_var) if down_var > 0 else 0.0
        if down_std > 0:
            sortino = Decimal(str(mean_r / down_std * math.sqrt(252)))

    time_in_market = None
    if equity_curve:
        in_market = sum(1 for s in equity_curve if s.open_positions > 0)
        time_in_market = _safe_div(Decimal(in_market), Decimal(len(equity_curve)))

    max_win_streak = 0
    max_loss_streak = 0
    win_streak = 0
    loss_streak = 0
    for t in closed:
        if t.net_pnl is not None and t.net_pnl > 0:
            win_streak += 1
            loss_streak = 0
        else:
            loss_streak += 1
            win_streak = 0
        max_win_streak = max(max_win_streak, win_streak)
        max_loss_streak = max(max_loss_streak, loss_streak)

    per_symbol: list[SymbolMetrics] = []
    symbols = sorted({t.symbol for t in closed})
    for sym in symbols:
        sym_trades = [t for t in closed if t.symbol == sym]
        sym_wins = [t for t in sym_trades if t.net_pnl and t.net_pnl > 0]
        per_symbol.append(
            SymbolMetrics(
                symbol=sym,
                trade_count=len(sym_trades),
                net_pnl=sum((t.net_pnl for t in sym_trades if t.net_pnl), Decimal("0")),
                win_rate=(
                    _safe_div(Decimal(len(sym_wins)), Decimal(len(sym_trades)))
                    if sym_trades
                    else None
                ),
            )
        )

    per_entry: list[EntryTypeMetrics] = []
    for et in ET:
        et_trades = [t for t in closed if t.entry_type == et]
        if not et_trades:
            continue
        et_wins = [t for t in et_trades if t.net_pnl and t.net_pnl > 0]
        per_entry.append(
            EntryTypeMetrics(
                entry_type=et,
                trade_count=len(et_trades),
                net_pnl=sum((t.net_pnl for t in et_trades if t.net_pnl), Decimal("0")),
                win_rate=_safe_div(Decimal(len(et_wins)), Decimal(len(et_trades))),
            )
        )

    return BacktestMetrics(
        total_return_pct=total_return,
        cagr_pct=cagr,
        max_drawdown_pct=max_dd,
        win_rate=win_rate,
        profit_factor=profit_factor,
        expectancy_usd=expectancy_usd,
        expectancy_r=expectancy_r,
        average_winner=avg_winner,
        average_loser=avg_loser,
        average_r_multiple=average_r,
        max_win_streak=max_win_streak,
        max_loss_streak=max_loss_streak,
        sharpe_ratio=sharpe,
        sortino_ratio=sortino,
        time_in_market_pct=time_in_market,
        trade_count=trade_count,
        total_fees=total_fees,
        total_funding=total_funding,
        total_slippage=total_slippage,
        per_symbol=tuple(per_symbol),
        per_entry_type=tuple(per_entry),
    )
