"""Risk Engine V1 — main evaluation orchestrator."""

from __future__ import annotations

from decimal import Decimal

from strategy_engine.models import ReasonCode

from risk_engine.models import (
    AccountState,
    OpenOrderState,
    PositionState,
    RiskDecision,
    RiskError,
    RiskParameters,
    SymbolConstraints,
    TradeProposal,
)
from risk_engine.portfolio import build_portfolio_snapshot, total_notional_usd
from risk_engine.rounding import round_to_tick
from risk_engine.sizing import (
    apply_risk_cap_after_rounding,
    cap_quantity_for_leverage,
    cap_quantity_for_margin,
    compute_position_sizing,
    compute_risk_budget,
)
from risk_engine.validation import (
    check_loss_limits,
    validate_account,
    validate_constraints,
    validate_long_stop,
    validate_open_positions,
    validate_parameters,
    validate_proposal,
)


def _reject(
    proposal: TradeProposal,
    *,
    reason_codes: tuple[ReasonCode, ...],
    errors: tuple[RiskError, ...],
    params: RiskParameters,
    current_open_risk_usd: Decimal | None = None,
) -> RiskDecision:
    return RiskDecision(
        approved=False,
        symbol=proposal.symbol,
        requested_entry_price=proposal.entry_price,
        requested_stop_price=proposal.stop_price,
        current_open_risk_usd=current_open_risk_usd,
        reason_codes=reason_codes,
        strategy_version=params.strategy_version,
        risk_specification_version=params.risk_specification_version,
        errors=errors,
    )


class RiskEngine:
    """Deterministic, fail-closed risk evaluation engine."""

    def evaluate(
        self,
        proposal: TradeProposal,
        account: AccountState,
        constraints: SymbolConstraints,
        open_positions: tuple[PositionState, ...] = (),
        open_orders: tuple[OpenOrderState, ...] = (),
        processed_intent_ids: frozenset[str] = frozenset(),
        params: RiskParameters | None = None,
    ) -> RiskDecision:
        """
        Evaluate a trade proposal against Specification Freeze 1.0 limits.

        No network, database, or system clock access.
        """
        p = params or RiskParameters()
        errors: list[RiskError] = []
        reason_codes: list[ReasonCode] = []

        params_err = validate_parameters(p)
        if params_err:
            return _reject(
                proposal,
                reason_codes=(params_err.code,),
                errors=(params_err,),
                params=p,
            )

        account_err = validate_account(account)
        if account_err:
            errors.append(account_err)
            reason_codes.append(account_err.code)
            return _reject(
                proposal,
                reason_codes=tuple(reason_codes),
                errors=tuple(errors),
                params=p,
            )

        constraint_err = validate_constraints(constraints)
        if constraint_err:
            errors.append(constraint_err)
            reason_codes.append(constraint_err.code)
            return _reject(
                proposal,
                reason_codes=tuple(reason_codes),
                errors=tuple(errors),
                params=p,
            )

        proposal_errors = validate_proposal(proposal)
        if proposal_errors:
            errors.extend(proposal_errors)
            reason_codes.extend(e.code for e in proposal_errors)
            return _reject(
                proposal,
                reason_codes=tuple(reason_codes),
                errors=tuple(errors),
                params=p,
            )

        positions_err = validate_open_positions(open_positions)
        if positions_err:
            return _reject(
                proposal,
                reason_codes=(positions_err.code,),
                errors=(positions_err,),
                params=p,
            )

        loss_err = check_loss_limits(account, p)
        if loss_err:
            errors.append(loss_err)
            reason_codes.append(loss_err.code)
            return _reject(
                proposal,
                reason_codes=tuple(reason_codes),
                errors=tuple(errors),
                params=p,
            )

        entry_price = proposal.entry_price
        stop_price = round_to_tick(proposal.stop_price, constraints.price_tick_size)

        stop_err = validate_long_stop(entry_price, stop_price)
        if stop_err:
            errors.append(stop_err)
            reason_codes.append(stop_err.code)
            return _reject(
                proposal,
                reason_codes=tuple(reason_codes),
                errors=tuple(errors),
                params=p,
            )

        if proposal.client_intent_id in processed_intent_ids:
            dup = RiskError(
                code=ReasonCode.RC_REJECT_DATA,
                message="Duplicate client_intent_id already processed",
            )
            errors.append(dup)
            reason_codes.append(dup.code)
            return _reject(
                proposal,
                reason_codes=tuple(reason_codes),
                errors=tuple(errors),
                params=p,
            )

        if any(pos.symbol == proposal.symbol for pos in open_positions):
            reason_codes.append(ReasonCode.RC_REJECT_DUPLICATE_SYMBOL)
            errors.append(
                RiskError(
                    code=ReasonCode.RC_REJECT_DUPLICATE_SYMBOL,
                    message="Position already open for symbol",
                )
            )
            return _reject(
                proposal,
                reason_codes=tuple(reason_codes),
                errors=tuple(errors),
                params=p,
            )

        if any(
            o.symbol == proposal.symbol and o.is_entry for o in open_orders
        ):
            reason_codes.append(ReasonCode.RC_REJECT_DUPLICATE_SYMBOL)
            errors.append(
                RiskError(
                    code=ReasonCode.RC_REJECT_DUPLICATE_SYMBOL,
                    message="Conflicting open entry order for symbol",
                )
            )
            return _reject(
                proposal,
                reason_codes=tuple(reason_codes),
                errors=tuple(errors),
                params=p,
            )

        if len(open_positions) >= p.max_open_positions:
            reason_codes.append(ReasonCode.RC_REJECT_MAX_POSITIONS)
            errors.append(
                RiskError(
                    code=ReasonCode.RC_REJECT_MAX_POSITIONS,
                    message="Maximum open positions reached",
                )
            )
            return _reject(
                proposal,
                reason_codes=tuple(reason_codes),
                errors=tuple(errors),
                params=p,
            )

        sizing = compute_position_sizing(
            equity_usd=account.equity_usd,
            entry_price=entry_price,
            stop_price=stop_price,
            quantity_step=constraints.quantity_step,
            minimum_quantity=constraints.minimum_quantity,
            params=p,
        )
        if sizing is None:
            reason_codes.append(ReasonCode.RC_REJECT_DATA)
            errors.append(
                RiskError(code=ReasonCode.RC_REJECT_DATA, message="Invalid stop distance")
            )
            return _reject(
                proposal,
                reason_codes=tuple(reason_codes),
                errors=tuple(errors),
                params=p,
            )

        if sizing.rounded_quantity <= 0:
            reason_codes.append(ReasonCode.RC_REJECT_RISK_TRADE)
            errors.append(
                RiskError(
                    code=ReasonCode.RC_REJECT_RISK_TRADE,
                    message="Quantity zero after rounding",
                )
            )
            return _reject(
                proposal,
                reason_codes=tuple(reason_codes),
                errors=tuple(errors),
                params=p,
            )

        quantity = sizing.rounded_quantity
        stop_distance = sizing.stop_distance_usd
        risk_budget = compute_risk_budget(account.equity_usd, p)
        existing_notional = total_notional_usd(open_positions)

        quantity = cap_quantity_for_leverage(
            quantity,
            entry_price=entry_price,
            equity_usd=account.equity_usd,
            total_notional_usd=existing_notional,
            quantity_step=constraints.quantity_step,
            max_leverage=p.max_leverage,
        )

        quantity = cap_quantity_for_margin(
            quantity,
            entry_price=entry_price,
            available_margin_usd=account.available_margin_usd,
            max_leverage=p.max_leverage,
            quantity_step=constraints.quantity_step,
        )

        capped = apply_risk_cap_after_rounding(
            quantity,
            stop_distance_usd=stop_distance,
            equity_usd=account.equity_usd,
            risk_budget_usd=risk_budget,
            quantity_step=constraints.quantity_step,
            minimum_quantity=constraints.minimum_quantity,
            params=p,
        )
        if capped is None or capped <= 0:
            reason_codes.append(ReasonCode.RC_REJECT_LEVERAGE)
            errors.append(
                RiskError(
                    code=ReasonCode.RC_REJECT_LEVERAGE,
                    message="Quantity insufficient after leverage/margin reduction",
                )
            )
            return _reject(
                proposal,
                reason_codes=tuple(reason_codes),
                errors=tuple(errors),
                params=p,
            )
        quantity = capped

        if quantity < constraints.minimum_quantity:
            reason_codes.append(ReasonCode.RC_REJECT_RISK_TRADE)
            errors.append(
                RiskError(
                    code=ReasonCode.RC_REJECT_RISK_TRADE,
                    message="Minimum quantity not met",
                )
            )
            return _reject(
                proposal,
                reason_codes=tuple(reason_codes),
                errors=tuple(errors),
                params=p,
            )

        notional = quantity * entry_price
        if notional < constraints.minimum_notional:
            reason_codes.append(ReasonCode.RC_REJECT_RISK_TRADE)
            errors.append(
                RiskError(
                    code=ReasonCode.RC_REJECT_RISK_TRADE,
                    message="Minimum notional not met",
                )
            )
            return _reject(
                proposal,
                reason_codes=tuple(reason_codes),
                errors=tuple(errors),
                params=p,
            )

        portfolio = build_portfolio_snapshot(
            equity_usd=account.equity_usd,
            positions=open_positions,
            new_entry_price=entry_price,
            new_quantity=quantity,
            new_stop_distance=stop_distance,
        )

        max_portfolio_risk_usd = account.equity_usd * p.max_portfolio_risk_pct
        if portfolio.projected_portfolio_risk_usd > max_portfolio_risk_usd:
            reason_codes.append(ReasonCode.RC_REJECT_RISK_PORTFOLIO)
            errors.append(
                RiskError(
                    code=ReasonCode.RC_REJECT_RISK_PORTFOLIO,
                    message="Projected portfolio risk exceeds limit",
                )
            )
            return _reject(
                proposal,
                reason_codes=tuple(reason_codes),
                errors=tuple(errors),
                params=p,
                current_open_risk_usd=portfolio.current_open_risk_usd,
            )

        if portfolio.effective_leverage > p.max_leverage:
            reason_codes.append(ReasonCode.RC_REJECT_LEVERAGE)
            errors.append(
                RiskError(
                    code=ReasonCode.RC_REJECT_LEVERAGE,
                    message="Effective leverage exceeds max_leverage",
                )
            )
            return _reject(
                proposal,
                reason_codes=tuple(reason_codes),
                errors=tuple(errors),
                params=p,
                current_open_risk_usd=portfolio.current_open_risk_usd,
            )

        required_margin = notional / p.max_leverage
        if required_margin > account.available_margin_usd:
            reason_codes.append(ReasonCode.RC_REJECT_LEVERAGE)
            errors.append(
                RiskError(
                    code=ReasonCode.RC_REJECT_LEVERAGE,
                    message="Insufficient available margin",
                )
            )
            return _reject(
                proposal,
                reason_codes=tuple(reason_codes),
                errors=tuple(errors),
                params=p,
                current_open_risk_usd=portfolio.current_open_risk_usd,
            )

        actual_risk = quantity * stop_distance
        return RiskDecision(
            approved=True,
            symbol=proposal.symbol,
            requested_entry_price=entry_price,
            requested_stop_price=stop_price,
            raw_quantity=sizing.raw_quantity,
            rounded_quantity=quantity,
            actual_trade_risk_usd=actual_risk,
            actual_trade_risk_pct=actual_risk / account.equity_usd,
            current_open_risk_usd=portfolio.current_open_risk_usd,
            projected_portfolio_risk_usd=portfolio.projected_portfolio_risk_usd,
            projected_portfolio_risk_pct=portfolio.projected_portfolio_risk_pct,
            required_margin_usd=required_margin,
            effective_leverage=portfolio.effective_leverage,
            reason_codes=(ReasonCode.RC_RISK_APPROVED,),
            strategy_version=p.strategy_version,
            risk_specification_version=p.risk_specification_version,
            errors=tuple(),
        )
