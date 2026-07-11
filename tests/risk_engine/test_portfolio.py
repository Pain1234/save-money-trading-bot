"""Unit tests for portfolio risk."""

from decimal import Decimal

from risk_engine.portfolio import current_open_risk_usd, open_risk_usd

from tests.risk_engine.conftest import make_position


class TestPortfolioRisk:
    def test_open_risk_with_trailing_stop(self) -> None:
        pos = make_position("BTC", "0.1", "95000", "89000", trail="91000", mark="96000")
        assert open_risk_usd(pos) == Decimal("0.1") * (Decimal("95000") - Decimal("91000"))

    def test_current_open_risk_sum(self) -> None:
        positions = (
            make_position("BTC", "0.1", "95000", "89000", trail="91000"),
            make_position("ETH", "1", "3000", "2800", trail="2900"),
        )
        total = current_open_risk_usd(positions)
        assert total == open_risk_usd(positions[0]) + open_risk_usd(positions[1])
