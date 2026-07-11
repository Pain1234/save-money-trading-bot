"""Fee, slippage, and funding application."""

from __future__ import annotations

from decimal import Decimal

from backtester.models import SlippageModel


def apply_entry_slippage(reference: Decimal, model: SlippageModel) -> Decimal:
    """Long entry: price worsens upward."""
    return reference * (Decimal("1") + model.slippage_bps / Decimal("10000"))


def apply_exit_slippage(reference: Decimal, model: SlippageModel) -> Decimal:
    """Long exit: price worsens downward."""
    return reference * (Decimal("1") - model.slippage_bps / Decimal("10000"))


def compute_fee(notional: Decimal, rate: Decimal) -> Decimal:
    return notional * rate


def compute_slippage_cost(reference: Decimal, fill: Decimal, quantity: Decimal) -> Decimal:
    return abs(fill - reference) * quantity


def compute_funding_payment(notional: Decimal, funding_rate: Decimal) -> Decimal:
    """Positive rate = long pays (cash decreases)."""
    return notional * funding_rate
