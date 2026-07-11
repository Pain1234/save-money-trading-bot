"""Integration tests for RiskEngine.evaluate."""

from decimal import Decimal

from risk_engine.engine import RiskEngine
from risk_engine.models import (
    AccountState,
    LossLimitConfig,
    MarketDataStatus,
    OpenOrderState,
    RiskParameters,
    TradeProposal,
    TradeSide,
)
from strategy_engine.models import ReasonCode, SignalIntentKind

from tests.risk_engine.conftest import (
    DEFAULT_CONSTRAINTS,
    make_account,
    make_long_proposal,
    make_position,
)


class TestRiskEngine:
    def test_approved_trade(self) -> None:
        engine = RiskEngine()
        decision = engine.evaluate(
            make_long_proposal(),
            make_account(),
            DEFAULT_CONSTRAINTS,
        )
        assert decision.approved is True
        assert decision.reason_codes == (ReasonCode.RC_RISK_APPROVED,)
        assert decision.rounded_quantity == Decimal("0.083")

    def test_stop_equals_entry_rejected(self) -> None:
        engine = RiskEngine()
        proposal = make_long_proposal(entry="95000", stop="95000")
        decision = engine.evaluate(proposal, make_account(), DEFAULT_CONSTRAINTS)
        assert not decision.approved
        assert ReasonCode.RC_REJECT_DATA in decision.reason_codes

    def test_stop_above_entry_rejected(self) -> None:
        engine = RiskEngine()
        proposal = make_long_proposal(entry="95000", stop="96000")
        decision = engine.evaluate(proposal, make_account(), DEFAULT_CONSTRAINTS)
        assert not decision.approved

    def test_negative_stop_rejected(self) -> None:
        engine = RiskEngine()
        proposal = make_long_proposal(entry="95000", stop="-1")
        decision = engine.evaluate(proposal, make_account(), DEFAULT_CONSTRAINTS)
        assert not decision.approved

    def test_zero_equity_rejected(self) -> None:
        engine = RiskEngine()
        decision = engine.evaluate(
            make_long_proposal(),
            AccountState(equity_usd=Decimal("0"), available_margin_usd=Decimal("0")),
            DEFAULT_CONSTRAINTS,
        )
        assert not decision.approved

    def test_negative_equity_rejected(self) -> None:
        engine = RiskEngine()
        decision = engine.evaluate(
            make_long_proposal(),
            AccountState(equity_usd=Decimal("-1"), available_margin_usd=Decimal("0")),
            DEFAULT_CONSTRAINTS,
        )
        assert not decision.approved

    def test_negative_margin_rejected(self) -> None:
        engine = RiskEngine()
        decision = engine.evaluate(
            make_long_proposal(),
            AccountState(equity_usd=Decimal("100000"), available_margin_usd=Decimal("-1")),
            DEFAULT_CONSTRAINTS,
        )
        assert not decision.approved

    def test_invalid_atr_rejected(self) -> None:
        engine = RiskEngine()
        proposal = make_long_proposal().model_copy(update={"atr14": Decimal("0")})
        decision = engine.evaluate(proposal, make_account(), DEFAULT_CONSTRAINTS)
        assert not decision.approved

    def test_invalid_quantity_step_rejected(self) -> None:
        engine = RiskEngine()
        bad = DEFAULT_CONSTRAINTS.model_copy(update={"quantity_step": Decimal("0")})
        decision = engine.evaluate(make_long_proposal(), make_account(), bad)
        assert not decision.approved

    def test_zero_minimum_notional_is_valid_when_exchange_has_no_minimum(self) -> None:
        constraints = DEFAULT_CONSTRAINTS.model_copy(
            update={"minimum_notional": Decimal("0")}
        )
        decision = RiskEngine().evaluate(
            make_long_proposal(), make_account(), constraints
        )
        assert decision.approved

    def test_min_quantity_not_met(self) -> None:
        engine = RiskEngine()
        tight = DEFAULT_CONSTRAINTS.model_copy(update={"minimum_quantity": Decimal("1")})
        decision = engine.evaluate(make_long_proposal(), make_account(), tight)
        assert not decision.approved
        assert ReasonCode.RC_REJECT_RISK_TRADE in decision.reason_codes

    def test_min_notional_not_met(self) -> None:
        engine = RiskEngine()
        tight = DEFAULT_CONSTRAINTS.model_copy(update={"minimum_notional": Decimal("10000000")})
        decision = engine.evaluate(make_long_proposal(), make_account(), tight)
        assert not decision.approved
        assert ReasonCode.RC_REJECT_RISK_TRADE in decision.reason_codes

    def test_portfolio_risk_at_limit(self) -> None:
        engine = RiskEngine()
        positions = (
            make_position("BTC", "0.083", "95000", "89000"),
            make_position("ETH", "0.083", "95000", "89000"),
        )
        decision = engine.evaluate(
            make_long_proposal(symbol="SOL", intent_id="intent-3"),
            make_account(),
            DEFAULT_CONSTRAINTS,
            open_positions=positions,
        )
        assert decision.approved is True
        assert decision.projected_portfolio_risk_pct <= Decimal("0.02")

    def test_portfolio_risk_exactly_two_percent_is_approved(self) -> None:
        position = make_position("ETH", "0.25", "10000", "4000", mark="10000")
        decision = RiskEngine().evaluate(
            make_long_proposal(symbol="SOL", entry="95000", stop="94500"),
            make_account(),
            DEFAULT_CONSTRAINTS,
            open_positions=(position,),
        )
        assert decision.approved
        assert decision.projected_portfolio_risk_usd == Decimal("2000")
        assert decision.projected_portfolio_risk_pct == Decimal("0.02")

    def test_portfolio_risk_over_limit(self) -> None:
        engine = RiskEngine()
        positions = (
            make_position("BTC", "0.083", "95000", "89000"),
            make_position("ETH", "0.083", "95000", "89000"),
            make_position("SOL", "0.083", "95000", "89000"),
        )
        decision = engine.evaluate(
            make_long_proposal(symbol="SOL", intent_id="intent-x"),
            make_account(),
            DEFAULT_CONSTRAINTS,
            open_positions=positions[:2],
        )
        assert decision.approved is True
        fourth = engine.evaluate(
            make_long_proposal(symbol="AVAX", intent_id="intent-4"),
            make_account(),
            DEFAULT_CONSTRAINTS,
            open_positions=positions,
        )
        assert not fourth.approved
        assert ReasonCode.RC_REJECT_MAX_POSITIONS in fourth.reason_codes

    def test_three_open_positions_rejected(self) -> None:
        engine = RiskEngine()
        positions = tuple(
            make_position(sym, "0.01", "95000", "89000")
            for sym in ("BTC", "ETH", "SOL")
        )
        decision = engine.evaluate(
            make_long_proposal(symbol="AVAX", intent_id="new"),
            make_account(),
            DEFAULT_CONSTRAINTS,
            open_positions=positions,
        )
        assert not decision.approved
        assert ReasonCode.RC_REJECT_MAX_POSITIONS in decision.reason_codes

    def test_symbol_already_open(self) -> None:
        engine = RiskEngine()
        decision = engine.evaluate(
            make_long_proposal(symbol="BTC"),
            make_account(),
            DEFAULT_CONSTRAINTS,
            open_positions=(make_position("BTC", "0.01", "95000", "89000"),),
        )
        assert not decision.approved
        assert ReasonCode.RC_REJECT_DUPLICATE_SYMBOL in decision.reason_codes

    def test_duplicate_intent_id(self) -> None:
        engine = RiskEngine()
        decision = engine.evaluate(
            make_long_proposal(intent_id="dup-1"),
            make_account(),
            DEFAULT_CONSTRAINTS,
            processed_intent_ids=frozenset({"dup-1"}),
        )
        assert not decision.approved
        assert ReasonCode.RC_REJECT_DATA in decision.reason_codes

    def test_leverage_never_increases_quantity(self) -> None:
        engine = RiskEngine()
        sizing_only = engine.evaluate(
            make_long_proposal(),
            make_account(equity="100000", margin="50000"),
            DEFAULT_CONSTRAINTS,
        )
        high_leverage_positions = (
            make_position("BTC", "1", "95000", "89000", mark="95000"),
        )
        capped = engine.evaluate(
            make_long_proposal(intent_id="intent-2"),
            make_account(equity="100000", margin="50000"),
            DEFAULT_CONSTRAINTS,
            open_positions=high_leverage_positions,
        )
        assert sizing_only.rounded_quantity is not None
        if capped.rounded_quantity is not None:
            assert capped.rounded_quantity <= sizing_only.rounded_quantity

    def test_insufficient_margin_rejected(self) -> None:
        engine = RiskEngine()
        decision = engine.evaluate(
            make_long_proposal(),
            make_account(equity="100000", margin="1"),
            DEFAULT_CONSTRAINTS,
        )
        assert not decision.approved
        assert ReasonCode.RC_REJECT_LEVERAGE in decision.reason_codes

    def test_invalid_market_data(self) -> None:
        engine = RiskEngine()
        proposal = make_long_proposal().model_copy(
            update={"market_data_status": MarketDataStatus.STALE}
        )
        decision = engine.evaluate(proposal, make_account(), DEFAULT_CONSTRAINTS)
        assert not decision.approved
        assert ReasonCode.RC_REJECT_DATA in decision.reason_codes

    def test_strategy_not_approved(self) -> None:
        engine = RiskEngine()
        proposal = make_long_proposal().model_copy(update={"strategy_approved": False})
        decision = engine.evaluate(proposal, make_account(), DEFAULT_CONSTRAINTS)
        assert not decision.approved
        assert ReasonCode.RC_REJECT_NO_SIGNAL in decision.reason_codes

    def test_strategy_approval_must_be_explicit(self) -> None:
        proposal = TradeProposal(
            symbol="BTC",
            entry_price=Decimal("95000"),
            stop_price=Decimal("89000"),
            client_intent_id="no-explicit-approval",
            signal_intent_kind=SignalIntentKind.LONG_ENTRY,
        )
        decision = RiskEngine().evaluate(proposal, make_account(), DEFAULT_CONSTRAINTS)
        assert not decision.approved
        assert ReasonCode.RC_REJECT_NO_SIGNAL in decision.reason_codes

    def test_frozen_max_leverage_cannot_be_raised(self) -> None:
        decision = RiskEngine().evaluate(
            make_long_proposal(),
            make_account(),
            DEFAULT_CONSTRAINTS,
            params=RiskParameters(max_leverage=Decimal("2.0001")),
        )
        assert not decision.approved
        assert ReasonCode.RC_REJECT_DATA in decision.reason_codes

    def test_negative_existing_position_size_is_rejected(self) -> None:
        position = make_position("ETH", "-1", "3000", "2800")
        decision = RiskEngine().evaluate(
            make_long_proposal(),
            make_account(),
            DEFAULT_CONSTRAINTS,
            open_positions=(position,),
        )
        assert not decision.approved
        assert ReasonCode.RC_REJECT_DATA in decision.reason_codes

    def test_nan_existing_mark_price_is_rejected(self) -> None:
        position = make_position("ETH", "1", "3000", "2800").model_copy(
            update={"mark_price": Decimal("NaN")}
        )
        decision = RiskEngine().evaluate(
            make_long_proposal(),
            make_account(),
            DEFAULT_CONSTRAINTS,
            open_positions=(position,),
        )
        assert not decision.approved
        assert ReasonCode.RC_REJECT_DATA in decision.reason_codes

    def test_short_proposal_rejected(self) -> None:
        engine = RiskEngine()
        proposal = make_long_proposal().model_copy(update={"side": TradeSide.SHORT})
        decision = engine.evaluate(proposal, make_account(), DEFAULT_CONSTRAINTS)
        assert not decision.approved

    def test_open_entry_order_collision(self) -> None:
        engine = RiskEngine()
        order = OpenOrderState(
            symbol="BTC",
            client_intent_id="pending-1",
            side=TradeSide.LONG,
            is_entry=True,
        )
        decision = engine.evaluate(
            make_long_proposal(symbol="BTC", intent_id="new-intent"),
            make_account(),
            DEFAULT_CONSTRAINTS,
            open_orders=(order,),
        )
        assert not decision.approved
        assert ReasonCode.RC_REJECT_DUPLICATE_SYMBOL in decision.reason_codes

    def test_daily_loss_limit_when_enabled(self) -> None:
        engine = RiskEngine()
        params = RiskParameters(
            loss_limits=LossLimitConfig(
                daily_loss_limit_enabled=True,
                max_daily_loss_pct=Decimal("0.01"),
            )
        )
        account = AccountState(
            equity_usd=Decimal("100000"),
            available_margin_usd=Decimal("50000"),
            daily_realized_pnl_usd=Decimal("-2000"),
        )
        decision = engine.evaluate(
            make_long_proposal(), account, DEFAULT_CONSTRAINTS, params=params
        )
        assert not decision.approved

    def test_optional_loss_limits_are_disabled_by_default(self) -> None:
        account = AccountState(
            equity_usd=Decimal("100000"),
            available_margin_usd=Decimal("50000"),
            daily_realized_pnl_usd=Decimal("-90000"),
            weekly_realized_pnl_usd=Decimal("-90000"),
            peak_equity_usd=Decimal("1000000"),
        )
        decision = RiskEngine().evaluate(
            make_long_proposal(), account, DEFAULT_CONSTRAINTS
        )
        assert decision.approved

    def test_daily_loss_exactly_at_enabled_limit_is_allowed(self) -> None:
        params = RiskParameters(
            loss_limits=LossLimitConfig(
                daily_loss_limit_enabled=True,
                max_daily_loss_pct=Decimal("0.01"),
            )
        )
        account = AccountState(
            equity_usd=Decimal("100000"),
            available_margin_usd=Decimal("50000"),
            daily_realized_pnl_usd=Decimal("-1000"),
        )
        decision = RiskEngine().evaluate(
            make_long_proposal(), account, DEFAULT_CONSTRAINTS, params=params
        )
        assert decision.approved

    def test_nan_daily_loss_is_rejected_when_limit_enabled(self) -> None:
        params = RiskParameters(
            loss_limits=LossLimitConfig(
                daily_loss_limit_enabled=True,
                max_daily_loss_pct=Decimal("0.01"),
            )
        )
        account = AccountState.model_construct(
            equity_usd=Decimal("100000"),
            available_margin_usd=Decimal("50000"),
            daily_realized_pnl_usd=Decimal("NaN"),
            weekly_realized_pnl_usd=Decimal("0"),
            peak_equity_usd=None,
        )
        decision = RiskEngine().evaluate(
            make_long_proposal(), account, DEFAULT_CONSTRAINTS, params=params
        )
        assert not decision.approved
        assert ReasonCode.RC_REJECT_DATA in decision.reason_codes

    def test_drawdown_limit_when_enabled(self) -> None:
        engine = RiskEngine()
        params = RiskParameters(
            loss_limits=LossLimitConfig(
                drawdown_limit_enabled=True,
                max_drawdown_pct=Decimal("0.05"),
            )
        )
        account = AccountState(
            equity_usd=Decimal("90000"),
            available_margin_usd=Decimal("50000"),
            peak_equity_usd=Decimal("100000"),
        )
        decision = engine.evaluate(
            make_long_proposal(), account, DEFAULT_CONSTRAINTS, params=params
        )
        assert not decision.approved

    def test_weekly_loss_limit_when_enabled(self) -> None:
        engine = RiskEngine()
        params = RiskParameters(
            loss_limits=LossLimitConfig(
                weekly_loss_limit_enabled=True,
                max_weekly_loss_pct=Decimal("0.01"),
            )
        )
        account = AccountState(
            equity_usd=Decimal("100000"),
            available_margin_usd=Decimal("50000"),
            weekly_realized_pnl_usd=Decimal("-1500"),
        )
        decision = engine.evaluate(
            make_long_proposal(), account, DEFAULT_CONSTRAINTS, params=params
        )
        assert not decision.approved

    def test_incomplete_market_data_rejected(self) -> None:
        engine = RiskEngine()
        proposal = make_long_proposal().model_copy(
            update={"market_data_status": MarketDataStatus.INCOMPLETE}
        )
        decision = engine.evaluate(proposal, make_account(), DEFAULT_CONSTRAINTS)
        assert not decision.approved

    def test_wrong_signal_intent_rejected(self) -> None:
        engine = RiskEngine()
        proposal = make_long_proposal().model_copy(
            update={"signal_intent_kind": SignalIntentKind.NO_ENTRY}
        )
        decision = engine.evaluate(proposal, make_account(), DEFAULT_CONSTRAINTS)
        assert not decision.approved
        assert ReasonCode.RC_REJECT_NO_SIGNAL in decision.reason_codes

    def test_portfolio_risk_slightly_over_limit(self) -> None:
        engine = RiskEngine()
        positions = (
            make_position("BTC", "0.083", "95000", "89000"),
            make_position("ETH", "0.083", "95000", "89000"),
        )
        params = RiskParameters(max_portfolio_risk_pct=Decimal("0.009"))
        decision = engine.evaluate(
            make_long_proposal(symbol="SOL", intent_id="i3"),
            make_account(),
            DEFAULT_CONSTRAINTS,
            open_positions=positions,
            params=params,
        )
        assert not decision.approved
        assert ReasonCode.RC_REJECT_RISK_PORTFOLIO in decision.reason_codes
