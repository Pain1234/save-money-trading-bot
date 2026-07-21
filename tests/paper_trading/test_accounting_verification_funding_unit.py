"""Unit coverage for funding checks in independent accounting (AUD-P1-011 / #386)."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

from paper_trading.accounting_verification import verify_accounting_independent
from paper_trading.enums import PaperFillKind


@dataclass
class _FakeRepo:
    wallet: SimpleNamespace
    fills: list = None  # type: ignore[assignment]
    positions: list = None  # type: ignore[assignment]
    funding_events: list = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        self.fills = self.fills or []
        self.positions = self.positions or []
        self.funding_events = self.funding_events or []

    def get_wallet(self):
        return self.wallet

    def list_all_fills(self):
        return self.fills

    def list_positions(self, limit: int = 10_000):
        return self.positions

    def get_open_positions(self):
        return [p for p in self.positions if getattr(p, "status", None) != "CLOSED"]

    def list_funding_events(self):
        return self.funding_events


def test_nonzero_funding_without_events_fails_closed() -> None:
    wallet = SimpleNamespace(
        cash=Decimal("100000"),
        total_fees=Decimal("0"),
        total_slippage=Decimal("0"),
        total_realized_pnl=Decimal("0"),
        total_funding=Decimal("12.34"),
    )
    repo = _FakeRepo(wallet=wallet)
    issues = verify_accounting_independent(repo, initial_cash=Decimal("100000"))  # type: ignore[arg-type]
    assert any("funding" in issue for issue in issues)


def test_funding_event_sum_matches_wallet() -> None:
    wallet = SimpleNamespace(
        cash=Decimal("100005"),
        total_fees=Decimal("0"),
        total_slippage=Decimal("0"),
        total_realized_pnl=Decimal("0"),
        total_funding=Decimal("5"),
    )
    event = SimpleNamespace(
        amount=Decimal("5"),
        deterministic_key="funding:once",
        funding_event_id=uuid4(),
    )
    repo = _FakeRepo(wallet=wallet, funding_events=[event])
    issues = verify_accounting_independent(repo, initial_cash=Decimal("100000"))  # type: ignore[arg-type]
    assert issues == []


def test_duplicate_funding_key_detected() -> None:
    wallet = SimpleNamespace(
        cash=Decimal("100010"),
        total_fees=Decimal("0"),
        total_slippage=Decimal("0"),
        total_realized_pnl=Decimal("0"),
        total_funding=Decimal("10"),
    )
    event_a = SimpleNamespace(amount=Decimal("5"), deterministic_key="dup")
    event_b = SimpleNamespace(amount=Decimal("5"), deterministic_key="dup")
    repo = _FakeRepo(wallet=wallet, funding_events=[event_a, event_b])
    issues = verify_accounting_independent(repo, initial_cash=Decimal("100000"))  # type: ignore[arg-type]
    assert any("duplicate funding event key" in issue for issue in issues)


# Keep fill enum import referenced for future fill-based fakes.
_ = PaperFillKind
