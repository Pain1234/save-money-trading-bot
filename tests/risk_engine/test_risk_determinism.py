"""Determinism and NaN/Infinity tests."""

from decimal import Decimal

from risk_engine.engine import RiskEngine
from risk_engine.models import AccountState

from tests.risk_engine.conftest import DEFAULT_CONSTRAINTS, make_account, make_long_proposal


class TestDeterminism:
    def test_identical_inputs_identical_outputs(self) -> None:
        engine = RiskEngine()
        proposal = make_long_proposal()
        account = make_account()
        r1 = engine.evaluate(proposal, account, DEFAULT_CONSTRAINTS)
        r2 = engine.evaluate(proposal, account, DEFAULT_CONSTRAINTS)
        assert r1.model_dump() == r2.model_dump()

    def test_multiple_proposals_independent(self) -> None:
        engine = RiskEngine()
        account = make_account()
        results = [
            engine.evaluate(
                make_long_proposal(intent_id=f"intent-{i}"),
                account,
                DEFAULT_CONSTRAINTS,
            )
            for i in range(3)
        ]
        assert all(r.approved for r in results)
        assert len({r.rounded_quantity for r in results}) == 1


class TestNanInfinity:
    def test_nan_equity_rejected(self) -> None:
        engine = RiskEngine()
        account = AccountState.model_construct(
            equity_usd=Decimal("NaN"),
            available_margin_usd=Decimal("1000"),
        )
        decision = engine.evaluate(make_long_proposal(), account, DEFAULT_CONSTRAINTS)
        assert not decision.approved

    def test_infinity_margin_rejected(self) -> None:
        engine = RiskEngine()
        account = AccountState.model_construct(
            equity_usd=Decimal("100000"),
            available_margin_usd=Decimal("Infinity"),
        )
        decision = engine.evaluate(make_long_proposal(), account, DEFAULT_CONSTRAINTS)
        assert not decision.approved
