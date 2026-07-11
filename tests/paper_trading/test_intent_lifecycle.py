"""Tests for trade intent lifecycle and transitions."""

from __future__ import annotations

import pytest
from paper_trading.enums import TradeIntentStatus
from paper_trading.transitions import InvalidTransitionError, validate_intent_transition


def test_valid_intent_transitions() -> None:
    validate_intent_transition(TradeIntentStatus.CREATED, TradeIntentStatus.SCHEDULED)
    validate_intent_transition(TradeIntentStatus.SCHEDULED, TradeIntentStatus.FILLED)


def test_invalid_intent_transition_rejected() -> None:
    with pytest.raises(InvalidTransitionError):
        validate_intent_transition(TradeIntentStatus.FILLED, TradeIntentStatus.SCHEDULED)


def test_terminal_intent_cannot_transition() -> None:
    with pytest.raises(InvalidTransitionError):
        validate_intent_transition(TradeIntentStatus.REJECTED, TradeIntentStatus.SCHEDULED)
