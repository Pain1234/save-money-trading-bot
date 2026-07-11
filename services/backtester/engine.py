"""Event-driven backtest engine."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal

from risk_engine.engine import RiskEngine
from risk_engine.models import SymbolConstraints
from strategy_engine.engine import StrategyEngine
from strategy_engine.models import (
    Candle,
    ReasonCode,
    SignalIntentKind,
    StrategyEvaluation,
    Timeframe,
    TrailingStopState,
)

from backtester.constants import INTRABAR_ASSUMPTION
from backtester.data import (
    build_candle_series,
    evaluation_time_for_daily,
    slice_closed_candles,
    validate_chronological,
)
from backtester.execution import compute_funding_payment
from backtester.intent import build_client_intent_id
from backtester.metrics import compute_drawdown_curve, compute_metrics
from backtester.models import (
    BacktestConfig,
    BacktestResult,
    BacktestTrade,
    EquitySnapshot,
    HistoricalDataBundle,
    OrderStatus,
    PendingIntent,
    RiskRejectionRecord,
    SimulatedOrder,
    SimulatedPosition,
    TrailingStopSnapshot,
)
from backtester.paper_lifecycle import (
    build_simulated_position_from_entry,
    compute_entry_accounting,
    compute_entry_fill_prices,
    compute_exit_accounting,
    compute_stop_trigger,
    compute_trailing_stop_update,
    evaluate_entry_risk_decision,
    filter_rejection_reason_codes,
)
from backtester.portfolio import (
    compute_equity,
    compute_unrealized_pnl,
    mark_prices_from_candles,
    prior_closes_from_timeline,
)


@dataclass
class _Runtime:
    cash: Decimal
    positions: dict[str, SimulatedPosition] = field(default_factory=dict)
    pending_intents: list[PendingIntent] = field(default_factory=list)
    processed_intent_ids: set[str] = field(default_factory=set)
    intent_orders: dict[str, SimulatedOrder] = field(default_factory=dict)
    active_trades: dict[str, BacktestTrade] = field(default_factory=dict)
    closed_trades: list[BacktestTrade] = field(default_factory=list)
    evaluations: list[StrategyEvaluation] = field(default_factory=list)
    rejections: list[RiskRejectionRecord] = field(default_factory=list)
    equity_curve: list[EquitySnapshot] = field(default_factory=list)
    total_fees: Decimal = Decimal("0")
    total_funding: Decimal = Decimal("0")
    total_slippage: Decimal = Decimal("0")
    realized_pnl: Decimal = Decimal("0")
    warnings: list[str] = field(default_factory=list)
    trail_history: dict[str, list[TrailingStopSnapshot]] = field(default_factory=dict)
    peak_equity: Decimal = Decimal("0")


class BacktestEngine:
    """Deterministic event-driven backtester using Strategy + Risk engines."""

    def __init__(self) -> None:
        self._strategy = StrategyEngine()
        self._risk = RiskEngine()

    def run(self, bundle: HistoricalDataBundle, config: BacktestConfig) -> BacktestResult:
        rt = _Runtime(cash=config.initial_cash)
        rt.peak_equity = config.initial_cash
        rt.processed_intent_ids = set(config.initial_processed_intent_ids)
        warnings = list(bundle.data_quality_warnings)

        for sym in config.symbols:
            for _key, candles in (
                ("daily", bundle.daily.get(sym, ())),
                ("weekly", bundle.weekly.get(sym, ())),
                ("monthly", bundle.monthly.get(sym, ())),
            ):
                warnings.extend(validate_chronological(candles))

        timeline = self._build_timeline(bundle, config.symbols)
        if not timeline:
            return self._empty_result(config, rt, warnings, None, None)

        data_start = timeline[0]
        data_end = timeline[-1]

        daily_by_sym: dict[str, dict[datetime, tuple[int, Candle]]] = {}
        for sym in config.symbols:
            candles = bundle.daily.get(sym, ())
            daily_by_sym[sym] = {c.open_time: (i, c) for i, c in enumerate(candles)}

        for _day_idx, open_time in enumerate(timeline):
            day_candles: dict[str, Candle] = {}
            for sym in config.symbols:
                entry = daily_by_sym[sym].get(open_time)
                if entry is None:
                    continue
                day_candles[sym] = entry[1]

            if not day_candles:
                continue

            closes = {s: c.close for s, c in day_candles.items()}
            prior_closes = prior_closes_from_timeline(
                daily_by_sym, config.symbols, open_time
            )

            for sym in config.symbols:
                if sym not in day_candles:
                    continue
                candle = day_candles[sym]
                self._fill_pending_at_open(
                    rt, config, sym, candle, day_candles, prior_closes
                )

            for sym in config.symbols:
                if sym not in day_candles:
                    continue
                candle = day_candles[sym]
                if sym in rt.positions:
                    self._check_stop_exit(rt, config, sym, candle)

            if config.funding_model.enabled:
                for sym in config.symbols:
                    if sym in rt.positions and sym in day_candles:
                        self._apply_funding(rt, bundle, sym, day_candles[sym])

            eval_time = evaluation_time_for_daily(list(day_candles.values())[0])
            for sym in config.symbols:
                if sym not in day_candles:
                    continue
                candle = day_candles[sym]
                eval_t = evaluation_time_for_daily(candle)
                self._strategy_and_queue(rt, config, bundle, sym, eval_t)

            for sym in config.symbols:
                if sym not in day_candles or sym not in rt.positions:
                    continue
                self._update_trailing(rt, config, bundle, sym, day_candles[sym], eval_time)

            marks = mark_prices_from_candles(tuple(rt.positions.values()), closes)
            unrealized = compute_unrealized_pnl(tuple(rt.positions.values()), marks)
            equity = rt.cash + unrealized
            rt.peak_equity = max(rt.peak_equity, equity)
            rt.equity_curve.append(
                EquitySnapshot(
                    time=eval_time,
                    cash=rt.cash,
                    equity=equity,
                    unrealized_pnl=unrealized,
                    open_positions=len(rt.positions),
                )
            )

        end_marks = {}
        if timeline:
            last = timeline[-1]
            for sym in config.symbols:
                entry = daily_by_sym[sym].get(last)
                if entry:
                    end_marks[sym] = entry[1].close
        end_equity = compute_equity(
            rt.cash, tuple(rt.positions.values()), end_marks
        )

        equity_tuple = tuple(rt.equity_curve)
        metrics = compute_metrics(
            trades=tuple(rt.closed_trades),
            equity_curve=equity_tuple,
            start_capital=config.initial_cash,
            end_capital=end_equity,
            total_fees=rt.total_fees,
            total_funding=rt.total_funding,
            total_slippage=rt.total_slippage,
            data_start=data_start,
            data_end=data_end,
        )

        assumptions = (
            "Perpetual margin accounting: wallet balance excludes reserved margin.",
            "Entry fill at next daily open after signal close, not at signal close.",
            "Risk evaluation uses actual fill price and fill-based initial stop.",
            "Open-fill marks use bar open or prior close, never same-day close.",
            f"Intrabar assumption: {INTRABAR_ASSUMPTION}",
            "Funding notional = quantity × entry_price (V1 model assumption).",
            "Symbol processing order follows BacktestConfig.symbols.",
            "Weekly/monthly candles filtered to closed only as of evaluation time.",
            "M4 portfolio gate ordering deferred (conservative leverage reduction).",
        )

        return BacktestResult(
            config=config,
            core_metadata=config.core_metadata,
            data_start=data_start,
            data_end=data_end,
            start_capital=config.initial_cash,
            end_capital=end_equity,
            trades=tuple(rt.closed_trades) + tuple(rt.active_trades.values()),
            open_positions=tuple(rt.positions.values()),
            equity_curve=equity_tuple,
            drawdown_curve=compute_drawdown_curve(equity_tuple),
            risk_rejections=tuple(rt.rejections),
            strategy_evaluations=tuple(rt.evaluations),
            total_fees=rt.total_fees,
            total_funding=rt.total_funding,
            total_slippage=rt.total_slippage,
            data_quality_warnings=tuple(warnings),
            model_assumptions=assumptions,
            funding_enabled=config.funding_model.enabled,
            metrics=metrics,
            processed_intent_ids=tuple(sorted(rt.processed_intent_ids)),
        )

    def _build_timeline(
        self,
        bundle: HistoricalDataBundle,
        symbols: tuple[str, ...],
    ) -> list[datetime]:
        times: set[datetime] = set()
        for sym in symbols:
            for c in bundle.daily.get(sym, ()):
                times.add(c.open_time)
        return sorted(times)

    def _get_constraints(self, config: BacktestConfig, symbol: str) -> SymbolConstraints:
        if symbol not in config.symbol_constraints:
            raise ValueError(f"Missing symbol constraints for {symbol}")
        return config.symbol_constraints[symbol]

    def _mark_terminal_intent(
        self,
        rt: _Runtime,
        intent: PendingIntent,
        status: OrderStatus,
        *,
        quantity: Decimal | None = None,
        reference_price: Decimal | None = None,
    ) -> None:
        rt.processed_intent_ids.add(intent.client_intent_id)
        rt.intent_orders[intent.client_intent_id] = SimulatedOrder(
            client_intent_id=intent.client_intent_id,
            symbol=intent.symbol,
            status=status,
            quantity=quantity,
            reference_price=reference_price,
        )

    def _fill_pending_at_open(
        self,
        rt: _Runtime,
        config: BacktestConfig,
        symbol: str,
        candle: Candle,
        day_candles: dict[str, Candle],
        prior_closes: dict[str, Decimal],
    ) -> None:
        to_fill = [p for p in rt.pending_intents if p.symbol == symbol]
        rt.pending_intents = [p for p in rt.pending_intents if p.symbol != symbol]

        for intent in to_fill:
            if intent.client_intent_id in rt.processed_intent_ids:
                continue

            constraints = self._get_constraints(config, symbol)
            open_ref = candle.open
            fill_prices = compute_entry_fill_prices(
                open_ref,
                intent.atr14,
                slippage_bps=config.slippage_model.slippage_bps,
                strategy_params=config.strategy_params,
                price_tick_size=constraints.price_tick_size,
            )
            fill = fill_prices.fill_price
            stop_init = fill_prices.stop_initial

            decision = evaluate_entry_risk_decision(
                self._risk,
                symbol=symbol,
                fill_price=fill,
                stop_initial=stop_init,
                client_intent_id=intent.client_intent_id,
                atr14=intent.atr14,
                constraints=constraints,
                wallet_cash=rt.cash,
                open_positions=tuple(rt.positions.values()),
                pending_intents=tuple(rt.pending_intents),
                processed_intent_ids=frozenset(rt.processed_intent_ids),
                day_candles=day_candles,
                prior_closes=prior_closes,
                risk_params=config.risk_params,
            )

            if not decision.approved or decision.rounded_quantity is None:
                reject_codes = filter_rejection_reason_codes(decision)
                self._mark_terminal_intent(rt, intent, OrderStatus.REJECTED)
                rt.rejections.append(
                    RiskRejectionRecord(
                        time=candle.open_time,
                        symbol=symbol,
                        client_intent_id=intent.client_intent_id,
                        reason_codes=reject_codes,
                        strategy_reason_codes=intent.strategy_reason_codes,
                    )
                )
                continue

            qty = decision.rounded_quantity
            accounting = compute_entry_accounting(
                fill_price=fill,
                open_ref=open_ref,
                quantity=qty,
                stop_initial=stop_init,
                fee_rate=config.fee_model.entry_fee_rate,
                slippage_bps=config.slippage_model.slippage_bps,
                max_leverage=config.risk_params.max_leverage,
                strategy_params=config.strategy_params,
                price_tick_size=constraints.price_tick_size,
                atr14=intent.atr14,
            )
            fee = accounting.fee
            slip = accounting.slippage_cost

            if fee > rt.cash:
                self._mark_terminal_intent(rt, intent, OrderStatus.REJECTED)
                rt.rejections.append(
                    RiskRejectionRecord(
                        time=candle.open_time,
                        symbol=symbol,
                        client_intent_id=intent.client_intent_id,
                        reason_codes=(ReasonCode.RC_REJECT_LEVERAGE,),
                        strategy_reason_codes=intent.strategy_reason_codes,
                    )
                )
                continue

            rt.cash -= fee
            rt.total_fees += fee
            rt.total_slippage += slip

            pos = build_simulated_position_from_entry(
                symbol=symbol,
                quantity=qty,
                fill_price=fill,
                entry_time=candle.open_time,
                accounting=accounting,
                atr14=intent.atr14,
                client_intent_id=intent.client_intent_id,
            )
            rt.positions[symbol] = pos
            rt.trail_history[symbol] = [
                TrailingStopSnapshot(
                    time=candle.open_time,
                    trail_stop=pos.trail_stop,
                    effective_stop=pos.effective_stop,
                )
            ]

            initial_risk = accounting.initial_risk_usd
            trade = BacktestTrade(
                symbol=symbol,
                client_intent_id=intent.client_intent_id,
                strategy_version=intent.strategy_version,
                entry_type=intent.entry_type,
                strategy_reason_codes=intent.strategy_reason_codes,
                risk_reason_codes=decision.reason_codes,
                signal_time=intent.signal_time,
                order_time=intent.order_time,
                entry_time=candle.open_time,
                entry_reference_price=open_ref,
                entry_fill_price=fill,
                quantity=qty,
                initial_stop=stop_init,
                trailing_stop_history=tuple(rt.trail_history[symbol]),
                fees=fee,
                slippage_cost=slip,
                initial_risk_usd=initial_risk,
            )
            rt.active_trades[symbol] = trade
            self._mark_terminal_intent(
                rt,
                intent,
                OrderStatus.FILLED,
                quantity=qty,
                reference_price=open_ref,
            )

            self._check_stop_exit(rt, config, symbol, candle)

    def _check_stop_exit(
        self,
        rt: _Runtime,
        config: BacktestConfig,
        symbol: str,
        candle: Candle,
    ) -> None:
        pos = rt.positions.get(symbol)
        if pos is None:
            return

        effective = pos.effective_stop
        trigger = compute_stop_trigger(
            candle,
            effective_stop=effective,
            initial_stop=pos.initial_stop,
            trail_stop=pos.trail_stop,
        )
        if trigger is None:
            return

        exit_ref = trigger.exit_reference
        reason = trigger.exit_reason

        exit_accounting = compute_exit_accounting(
            exit_reference=exit_ref,
            quantity=pos.quantity,
            entry_price=pos.entry_price,
            slippage_bps=config.slippage_model.slippage_bps,
            fee_rate=config.fee_model.exit_fee_rate,
        )
        fill = exit_accounting.fill_price
        fee = exit_accounting.fee
        slip = exit_accounting.slippage_cost
        gross = exit_accounting.gross_pnl

        rt.cash += exit_accounting.net_wallet_delta
        rt.total_fees += fee
        rt.total_slippage += slip

        trade = rt.active_trades.pop(symbol, None)
        if trade:
            total_trade_fees = trade.fees + fee
            total_slip = trade.slippage_cost + slip
            net = gross - total_trade_fees - trade.funding
            r_mult = _safe_r(trade.initial_risk_usd, net)
            days = (candle.open_time - trade.entry_time).days
            closed = trade.model_copy(
                update={
                    "exit_time": candle.open_time,
                    "exit_reason": reason,
                    "exit_reference_price": exit_ref,
                    "exit_fill_price": fill,
                    "gross_pnl": gross,
                    "fees": total_trade_fees,
                    "slippage_cost": total_slip,
                    "net_pnl": net,
                    "r_multiple": r_mult,
                    "holding_period_days": days,
                    "trailing_stop_history": tuple(rt.trail_history.get(symbol, [])),
                }
            )
            rt.closed_trades.append(closed)
            rt.realized_pnl += net

        del rt.positions[symbol]
        rt.trail_history.pop(symbol, None)

    def _apply_funding(
        self,
        rt: _Runtime,
        bundle: HistoricalDataBundle,
        symbol: str,
        candle: Candle,
    ) -> None:
        pos = rt.positions.get(symbol)
        if pos is None:
            return
        events = bundle.funding.get(symbol, ())
        for ev in events:
            if not (candle.open_time <= ev.timestamp <= candle.close_time):
                continue
            notional = pos.quantity * pos.entry_price
            payment = compute_funding_payment(notional, ev.funding_rate)
            rt.cash -= payment
            rt.total_funding += payment
            trade = rt.active_trades.get(symbol)
            if trade:
                rt.active_trades[symbol] = trade.model_copy(
                    update={"funding": trade.funding + payment}
                )

    def _strategy_and_queue(
        self,
        rt: _Runtime,
        config: BacktestConfig,
        bundle: HistoricalDataBundle,
        symbol: str,
        eval_time: datetime,
    ) -> None:
        daily = build_candle_series(
            symbol, Timeframe.DAILY, bundle.daily.get(symbol, ()), eval_time
        )
        weekly = build_candle_series(
            symbol, Timeframe.WEEKLY, bundle.weekly.get(symbol, ()), eval_time
        )
        monthly = build_candle_series(
            symbol, Timeframe.MONTHLY, bundle.monthly.get(symbol, ()), eval_time
        )

        evaluation = self._strategy.evaluate(
            daily, weekly, monthly, eval_time, config.strategy_params
        )
        rt.evaluations.append(evaluation)

        if evaluation.signal_intent.kind != SignalIntentKind.LONG_ENTRY:
            return
        if evaluation.selected_entry_type is None:
            return
        if evaluation.signal_intent.stop_initial is None:
            return
        if evaluation.atr is None:
            return

        intent_id = build_client_intent_id(
            symbol,
            evaluation.strategy_version,
            eval_time,
            evaluation.selected_entry_type,
        )
        if intent_id in rt.processed_intent_ids:
            return
        if symbol in rt.positions:
            return
        if any(p.symbol == symbol for p in rt.pending_intents):
            return

        rt.pending_intents.append(
            PendingIntent(
                client_intent_id=intent_id,
                symbol=symbol,
                strategy_version=evaluation.strategy_version,
                entry_type=evaluation.selected_entry_type,
                strategy_reason_codes=evaluation.reason_codes,
                signal_time=eval_time,
                order_time=eval_time,
                signal_close_price=evaluation.signal_intent.entry_price or Decimal("0"),
                stop_price=evaluation.signal_intent.stop_initial,
                atr14=evaluation.atr,
                strategy_evaluation=evaluation,
            )
        )

    def _update_trailing(
        self,
        rt: _Runtime,
        config: BacktestConfig,
        bundle: HistoricalDataBundle,
        symbol: str,
        candle: Candle,
        eval_time: datetime,
    ) -> None:
        pos = rt.positions.get(symbol)
        if pos is None:
            return

        daily_closed = slice_closed_candles(bundle.daily.get(symbol, ()), eval_time)
        if not daily_closed:
            return

        eval_copy = next(
            (e for e in reversed(rt.evaluations) if e.symbol == symbol),
            None,
        )
        atr = eval_copy.atr if eval_copy and eval_copy.atr else pos.entry_atr14

        state = TrailingStopState(
            entry_price=pos.entry_price,
            stop_initial=pos.initial_stop,
            highest_close=pos.highest_close,
            trail_stop=pos.trail_stop,
            effective_stop=pos.effective_stop,
        )
        constraints = self._get_constraints(config, symbol)
        updated = compute_trailing_stop_update(
            state,
            candle.close,
            atr,
            config.strategy_params,
            constraints.price_tick_size,
        )

        new_pos = pos.model_copy(
            update={
                "trail_stop": updated.trail_stop,
                "effective_stop": updated.effective_stop,
                "highest_close": updated.highest_close,
            }
        )
        rt.positions[symbol] = new_pos
        rt.trail_history.setdefault(symbol, []).append(
            TrailingStopSnapshot(
                time=eval_time,
                trail_stop=updated.trail_stop,
                effective_stop=updated.effective_stop,
            )
        )

    def _empty_result(
        self,
        config: BacktestConfig,
        rt: _Runtime,
        warnings: list[str],
        start: datetime | None,
        end: datetime | None,
    ) -> BacktestResult:
        metrics = compute_metrics(
            trades=(),
            equity_curve=(),
            start_capital=config.initial_cash,
            end_capital=config.initial_cash,
            total_fees=Decimal("0"),
            total_funding=Decimal("0"),
            total_slippage=Decimal("0"),
            data_start=start,
            data_end=end,
        )
        return BacktestResult(
            config=config,
            core_metadata=config.core_metadata,
            data_start=start,
            data_end=end,
            start_capital=config.initial_cash,
            end_capital=config.initial_cash,
            trades=(),
            open_positions=(),
            equity_curve=(),
            drawdown_curve=(),
            risk_rejections=(),
            strategy_evaluations=(),
            total_fees=Decimal("0"),
            total_funding=Decimal("0"),
            total_slippage=Decimal("0"),
            data_quality_warnings=tuple(warnings),
            model_assumptions=("No data timeline.",),
            funding_enabled=config.funding_model.enabled,
            metrics=metrics,
            processed_intent_ids=(),
        )


def _safe_r(initial_risk: Decimal | None, net_pnl: Decimal) -> Decimal | None:
    if initial_risk is None or initial_risk == 0:
        return None
    return net_pnl / initial_risk
