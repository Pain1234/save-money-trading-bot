"""Unit tests for position sizing."""

from decimal import Decimal

from risk_engine.models import RiskParameters
from risk_engine.rounding import floor_to_step
from risk_engine.sizing import compute_position_sizing


class TestPositionSizing:
    def test_basic_position_size(self) -> None:
        params = RiskParameters()
        result = compute_position_sizing(
            equity_usd=Decimal("100000"),
            entry_price=Decimal("95000"),
            stop_price=Decimal("89000"),
            quantity_step=Decimal("0.001"),
            minimum_quantity=Decimal("0.001"),
            params=params,
        )
        assert result is not None
        assert result.risk_budget_usd == Decimal("500")
        assert result.stop_distance_usd == Decimal("6000")
        assert result.rounded_quantity == Decimal("0.083")
        assert result.actual_trade_risk_usd == Decimal("498")
        assert result.actual_trade_risk_usd <= result.risk_budget_usd

    def test_decimal_precision(self) -> None:
        result = compute_position_sizing(
            equity_usd=Decimal("100000.55"),
            entry_price=Decimal("95000.12"),
            stop_price=Decimal("89000.07"),
            quantity_step=Decimal("0.001"),
            minimum_quantity=Decimal("0.001"),
            params=RiskParameters(),
        )
        assert result is not None
        assert isinstance(result.raw_quantity, Decimal)

    def test_floor_to_quantity_step(self) -> None:
        assert floor_to_step(Decimal("0.08333"), Decimal("0.001")) == Decimal("0.083")

    def test_floor_to_very_small_quantity_step_never_rounds_up(self) -> None:
        value = Decimal("0.000000019999999999")
        step = Decimal("0.000000000001")
        rounded = floor_to_step(value, step)
        assert rounded == Decimal("0.000000019999")
        assert rounded <= value

    def test_stop_above_entry_fails_closed(self) -> None:
        result = compute_position_sizing(
            equity_usd=Decimal("100000"),
            entry_price=Decimal("95000"),
            stop_price=Decimal("96000"),
            quantity_step=Decimal("0.001"),
            minimum_quantity=Decimal("0.001"),
            params=RiskParameters(),
        )
        assert result is None

    def test_risk_recheck_after_rounding(self) -> None:
        result = compute_position_sizing(
            equity_usd=Decimal("100000"),
            entry_price=Decimal("95000"),
            stop_price=Decimal("89000"),
            quantity_step=Decimal("0.001"),
            minimum_quantity=Decimal("0.001"),
            params=RiskParameters(),
        )
        assert result is not None
        limit = Decimal("100000") * Decimal("0.005")
        assert result.actual_trade_risk_usd <= limit

    def test_zero_quantity_after_rounding(self) -> None:
        result = compute_position_sizing(
            equity_usd=Decimal("100"),
            entry_price=Decimal("95000"),
            stop_price=Decimal("89000"),
            quantity_step=Decimal("0.001"),
            minimum_quantity=Decimal("0.001"),
            params=RiskParameters(),
        )
        assert result is not None
        assert result.rounded_quantity == Decimal("0")
