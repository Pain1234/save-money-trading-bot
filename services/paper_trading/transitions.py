"""Valid state transitions for paper trading domain entities."""

from __future__ import annotations

from paper_trading.enums import (
    PaperOrderStatus,
    RuntimeStatus,
    TradeIntentStatus,
)

TERMINAL_INTENT_STATUSES: frozenset[TradeIntentStatus] = frozenset(
    {
        TradeIntentStatus.REJECTED,
        TradeIntentStatus.CANCELLED,
        TradeIntentStatus.EXPIRED,
        TradeIntentStatus.FAILED,
        TradeIntentStatus.FILLED,
    }
)

TERMINAL_ORDER_STATUSES: frozenset[PaperOrderStatus] = frozenset(
    {
        PaperOrderStatus.REJECTED,
        PaperOrderStatus.CANCELLED,
        PaperOrderStatus.EXPIRED,
        PaperOrderStatus.FILLED,
    }
)

_INTENT_TRANSITIONS: dict[TradeIntentStatus, frozenset[TradeIntentStatus]] = {
    TradeIntentStatus.CREATED: frozenset(
        {
            TradeIntentStatus.APPROVED,
            TradeIntentStatus.SCHEDULED,
            TradeIntentStatus.REJECTED,
            TradeIntentStatus.CANCELLED,
            TradeIntentStatus.FAILED,
        }
    ),
    TradeIntentStatus.APPROVED: frozenset(
        {
            TradeIntentStatus.SCHEDULED,
            TradeIntentStatus.SUBMITTED_TO_PAPER_ENGINE,
            TradeIntentStatus.REJECTED,
            TradeIntentStatus.CANCELLED,
            TradeIntentStatus.FAILED,
            TradeIntentStatus.EXPIRED,
        }
    ),
    TradeIntentStatus.SCHEDULED: frozenset(
        {
            TradeIntentStatus.SUBMITTED_TO_PAPER_ENGINE,
            TradeIntentStatus.FILLED,
            TradeIntentStatus.REJECTED,
            TradeIntentStatus.CANCELLED,
            TradeIntentStatus.FAILED,
            TradeIntentStatus.EXPIRED,
        }
    ),
    TradeIntentStatus.SUBMITTED_TO_PAPER_ENGINE: frozenset(
        {
            TradeIntentStatus.FILLED,
            TradeIntentStatus.REJECTED,
            TradeIntentStatus.FAILED,
        }
    ),
}

_ORDER_TRANSITIONS: dict[PaperOrderStatus, frozenset[PaperOrderStatus]] = {
    PaperOrderStatus.PENDING: frozenset(
        {
            PaperOrderStatus.OPEN,
            PaperOrderStatus.REJECTED,
            PaperOrderStatus.CANCELLED,
            PaperOrderStatus.EXPIRED,
        }
    ),
    PaperOrderStatus.OPEN: frozenset(
        {
            PaperOrderStatus.FILLED,
            PaperOrderStatus.REJECTED,
            PaperOrderStatus.CANCELLED,
            PaperOrderStatus.EXPIRED,
        }
    ),
}

_RUNTIME_TRANSITIONS: dict[RuntimeStatus, frozenset[RuntimeStatus]] = {
    RuntimeStatus.STOPPED: frozenset({RuntimeStatus.STARTING}),
    RuntimeStatus.STARTING: frozenset(
        {RuntimeStatus.RECOVERING, RuntimeStatus.SYNCING, RuntimeStatus.FAILED}
    ),
    RuntimeStatus.RECOVERING: frozenset(
        {RuntimeStatus.SYNCING, RuntimeStatus.READY, RuntimeStatus.DEGRADED, RuntimeStatus.FAILED}
    ),
    RuntimeStatus.SYNCING: frozenset(
        {RuntimeStatus.READY, RuntimeStatus.DEGRADED, RuntimeStatus.FAILED}
    ),
    RuntimeStatus.READY: frozenset(
        {
            RuntimeStatus.DEGRADED,
            RuntimeStatus.FAILED,
            RuntimeStatus.PAUSED,
            RuntimeStatus.KILLED,
            RuntimeStatus.SHUTTING_DOWN,
        }
    ),
    # DEGRADED is non-terminal: after process exit or redeploy the new worker must
    # enter startup recovery (RECOVERING) before returning to READY or DEGRADED.
    RuntimeStatus.DEGRADED: frozenset(
        {
            RuntimeStatus.RECOVERING,
            RuntimeStatus.READY,
            RuntimeStatus.PAUSED,
            RuntimeStatus.KILLED,
            RuntimeStatus.SHUTTING_DOWN,
            RuntimeStatus.FAILED,
        }
    ),
    RuntimeStatus.PAUSED: frozenset({RuntimeStatus.READY, RuntimeStatus.SHUTTING_DOWN}),
    RuntimeStatus.KILLED: frozenset({RuntimeStatus.SHUTTING_DOWN}),
    RuntimeStatus.SHUTTING_DOWN: frozenset({RuntimeStatus.STOPPED, RuntimeStatus.FAILED}),
}


class InvalidTransitionError(ValueError):
    """Raised when a domain state transition is not allowed."""


def validate_intent_transition(
    current: TradeIntentStatus,
    target: TradeIntentStatus,
) -> None:
    if current == target:
        return
    if current in TERMINAL_INTENT_STATUSES:
        raise InvalidTransitionError(f"intent already terminal: {current}")
    allowed = _INTENT_TRANSITIONS.get(current, frozenset())
    if target not in allowed:
        raise InvalidTransitionError(f"invalid intent transition {current} -> {target}")


def validate_order_transition(
    current: PaperOrderStatus,
    target: PaperOrderStatus,
) -> None:
    if current == target:
        return
    if current in TERMINAL_ORDER_STATUSES:
        raise InvalidTransitionError(f"order already terminal: {current}")
    allowed = _ORDER_TRANSITIONS.get(current, frozenset())
    if target not in allowed:
        raise InvalidTransitionError(f"invalid order transition {current} -> {target}")


def validate_runtime_transition(
    current: RuntimeStatus,
    target: RuntimeStatus,
) -> None:
    if current == target:
        return
    allowed = _RUNTIME_TRANSITIONS.get(current, frozenset())
    if target not in allowed:
        raise InvalidTransitionError(f"invalid runtime transition {current} -> {target}")
