"""Input validation — fail-closed."""

from __future__ import annotations

import math
from decimal import Decimal

from strategy_engine.models import ReasonCode, SignalIntentKind

from risk_engine.constants import (
    DEFAULT_MAX_LEVERAGE,
    DEFAULT_MAX_OPEN_POSITIONS,
    DEFAULT_MAX_PORTFOLIO_RISK_PCT,
    DEFAULT_RISK_PER_TRADE_PCT,
)
from risk_engine.models import (
    AccountState,
    BotSystemState,
    MarketDataStatus,
    PositionState,
    RiskError,
    RiskParameters,
    SymbolConstraints,
    TradeProposal,
    TradeSide,
)


def _is_finite(value: Decimal) -> bool:
    try:
        f = float(value)
    except (OverflowError, ValueError):
        return False
    return math.isfinite(f)


def validate_account(account: AccountState) -> RiskError | None:
    if not _is_finite(account.equity_usd) or not _is_finite(account.available_margin_usd):
        return RiskError(
            code=ReasonCode.RC_REJECT_DATA,
            message="Account values must be finite",
        )
    if account.equity_usd <= 0:
        return RiskError(
            code=ReasonCode.RC_REJECT_DATA,
            message="Equity must be greater than zero",
        )
    if account.available_margin_usd < 0:
        return RiskError(
            code=ReasonCode.RC_REJECT_DATA,
            message="Available margin must not be negative",
        )
    return None


def validate_constraints(constraints: SymbolConstraints) -> RiskError | None:
    for name, val in (
        ("quantity_step", constraints.quantity_step),
        ("minimum_quantity", constraints.minimum_quantity),
        ("minimum_notional", constraints.minimum_notional),
        ("price_tick_size", constraints.price_tick_size),
    ):
        invalid = val < 0 if name == "minimum_notional" else val <= 0
        if not _is_finite(val) or invalid:
            return RiskError(
                code=ReasonCode.RC_REJECT_DATA,
                message=f"Invalid {name}",
                details={name: str(val)},
            )
    return None


def validate_parameters(params: RiskParameters) -> RiskError | None:
    decimal_limits = (
        ("risk_per_trade_pct", params.risk_per_trade_pct, DEFAULT_RISK_PER_TRADE_PCT),
        (
            "max_portfolio_risk_pct",
            params.max_portfolio_risk_pct,
            DEFAULT_MAX_PORTFOLIO_RISK_PCT,
        ),
        ("max_leverage", params.max_leverage, DEFAULT_MAX_LEVERAGE),
    )
    for name, value, frozen_maximum in decimal_limits:
        if not _is_finite(value) or value <= 0 or value > frozen_maximum:
            return RiskError(
                code=ReasonCode.RC_REJECT_DATA,
                message=f"Invalid {name} for Specification Freeze 1.0",
                details={name: str(value), "maximum": str(frozen_maximum)},
            )
    if params.max_open_positions <= 0 or params.max_open_positions > DEFAULT_MAX_OPEN_POSITIONS:
        return RiskError(
            code=ReasonCode.RC_REJECT_DATA,
            message="Invalid max_open_positions for Specification Freeze 1.0",
        )
    if not _is_finite(params.risk_rounding_tolerance) or params.risk_rounding_tolerance < 0:
        return RiskError(
            code=ReasonCode.RC_REJECT_DATA,
            message="Invalid risk_rounding_tolerance",
        )
    return None


def validate_open_positions(positions: tuple[PositionState, ...]) -> RiskError | None:
    seen_symbols: set[str] = set()
    for position in positions:
        if not position.symbol or position.symbol in seen_symbols:
            return RiskError(
                code=ReasonCode.RC_REJECT_DATA,
                message="Invalid or duplicate symbol in open positions",
            )
        seen_symbols.add(position.symbol)
        for name, value in (
            ("entry_price", position.entry_price),
            ("position_size", position.position_size),
            ("stop_initial", position.stop_initial),
            ("trail_stop", position.trail_stop),
            ("mark_price", position.mark_price),
        ):
            if not _is_finite(value) or value <= 0:
                return RiskError(
                    code=ReasonCode.RC_REJECT_DATA,
                    message=f"Invalid open-position {name}",
                    details={"symbol": position.symbol, name: str(value)},
                )
        if position.stop_initial >= position.entry_price:
            return RiskError(
                code=ReasonCode.RC_REJECT_DATA,
                message="Open-position initial stop must be below entry price",
                details={"symbol": position.symbol},
            )
    return None


def validate_proposal(proposal: TradeProposal) -> list[RiskError]:
    errors: list[RiskError] = []

    if proposal.side != TradeSide.LONG:
        errors.append(
            RiskError(
                code=ReasonCode.RC_REJECT_DATA,
                message="V1 is long-only; short proposals rejected",
            )
        )

    for name, val in (("entry_price", proposal.entry_price), ("stop_price", proposal.stop_price)):
        if not _is_finite(val) or val <= 0:
            errors.append(
                RiskError(
                    code=ReasonCode.RC_REJECT_DATA,
                    message=f"Invalid {name}",
                )
            )

    if proposal.atr14 is not None and (not _is_finite(proposal.atr14) or proposal.atr14 <= 0):
        errors.append(
            RiskError(
                code=ReasonCode.RC_REJECT_DATA,
                message="Invalid ATR14",
            )
        )

    if proposal.signal_intent_kind != SignalIntentKind.LONG_ENTRY:
        errors.append(
            RiskError(
                code=ReasonCode.RC_REJECT_NO_SIGNAL,
                message="Signal intent must be LONG_ENTRY",
            )
        )

    if not proposal.strategy_approved:
        errors.append(
            RiskError(
                code=ReasonCode.RC_REJECT_NO_SIGNAL,
                message="Strategy approval missing",
            )
        )

    if proposal.market_data_status != MarketDataStatus.OK:
        errors.append(
            RiskError(
                code=ReasonCode.RC_REJECT_DATA,
                message="Market data not OK",
                details={"status": proposal.market_data_status.value},
            )
        )

    if proposal.bot_system_state not in (BotSystemState.ACTIVE,):
        errors.append(
            RiskError(
                code=ReasonCode.RC_REJECT_DATA,
                message="Bot system state does not allow entries",
                details={"state": proposal.bot_system_state.value},
            )
        )

    return errors


def validate_long_stop(entry_price: Decimal, stop_price: Decimal) -> RiskError | None:
    if stop_price >= entry_price:
        return RiskError(
            code=ReasonCode.RC_REJECT_DATA,
            message="Long stop must be below entry price",
        )
    distance = entry_price - stop_price
    if distance <= 0:
        return RiskError(
            code=ReasonCode.RC_REJECT_DATA,
            message="Stop distance must be positive",
        )
    return None


def check_loss_limits(
    account: AccountState,
    params: RiskParameters,
) -> RiskError | None:
    """Optional loss/drawdown limits — disabled by default in V1."""
    cfg = params.loss_limits

    if cfg.daily_loss_limit_enabled:
        if (
            cfg.max_daily_loss_pct is None
            or not _is_finite(cfg.max_daily_loss_pct)
            or cfg.max_daily_loss_pct < 0
            or not _is_finite(account.daily_realized_pnl_usd)
        ):
            return RiskError(
                code=ReasonCode.RC_REJECT_DATA,
                message="Daily loss limit configuration or account value invalid",
            )
        if account.daily_realized_pnl_usd < 0:
            loss_pct = abs(account.daily_realized_pnl_usd) / account.equity_usd
            if loss_pct > cfg.max_daily_loss_pct:
                return RiskError(
                    code=ReasonCode.RC_REJECT_DATA,
                    message="Daily loss limit reached",
                )

    if cfg.weekly_loss_limit_enabled:
        if (
            cfg.max_weekly_loss_pct is None
            or not _is_finite(cfg.max_weekly_loss_pct)
            or cfg.max_weekly_loss_pct < 0
            or not _is_finite(account.weekly_realized_pnl_usd)
        ):
            return RiskError(
                code=ReasonCode.RC_REJECT_DATA,
                message="Weekly loss limit configuration or account value invalid",
            )
        if account.weekly_realized_pnl_usd < 0:
            loss_pct = abs(account.weekly_realized_pnl_usd) / account.equity_usd
            if loss_pct > cfg.max_weekly_loss_pct:
                return RiskError(
                    code=ReasonCode.RC_REJECT_DATA,
                    message="Weekly loss limit reached",
                )

    if cfg.drawdown_limit_enabled:
        if (
            cfg.max_drawdown_pct is None
            or not _is_finite(cfg.max_drawdown_pct)
            or cfg.max_drawdown_pct < 0
            or account.peak_equity_usd is None
            or not _is_finite(account.peak_equity_usd)
            or account.peak_equity_usd <= 0
        ):
            return RiskError(
                code=ReasonCode.RC_REJECT_DATA,
                message="Drawdown limit enabled but configuration incomplete",
            )
        drawdown = (account.peak_equity_usd - account.equity_usd) / account.peak_equity_usd
        if drawdown > cfg.max_drawdown_pct:
            return RiskError(
                code=ReasonCode.RC_REJECT_DATA,
                message="Drawdown limit reached",
            )

    return None
