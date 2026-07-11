"""String enums for the paper trading orchestrator domain."""

from __future__ import annotations

from enum import StrEnum


class RuntimeStatus(StrEnum):
    STOPPED = "STOPPED"
    STARTING = "STARTING"
    RECOVERING = "RECOVERING"
    SYNCING = "SYNCING"
    READY = "READY"
    DEGRADED = "DEGRADED"
    PAUSED = "PAUSED"
    KILLED = "KILLED"
    SHUTTING_DOWN = "SHUTTING_DOWN"
    FAILED = "FAILED"


class TradeIntentStatus(StrEnum):
    CREATED = "CREATED"
    APPROVED = "APPROVED"
    SCHEDULED = "SCHEDULED"
    SUBMITTED_TO_PAPER_ENGINE = "SUBMITTED_TO_PAPER_ENGINE"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FILLED = "FILLED"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"
    FAILED = "FAILED"


class PaperOrderStatus(StrEnum):
    PENDING = "PENDING"
    OPEN = "OPEN"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FILLED = "FILLED"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"


class PaperPositionStatus(StrEnum):
    OPEN = "OPEN"
    CLOSING = "CLOSING"
    CLOSED = "CLOSED"


class PaperOrderType(StrEnum):
    MARKET_AT_OPEN = "MARKET_AT_OPEN"
    STOP_MARKET = "STOP_MARKET"


class PaperSide(StrEnum):
    LONG = "LONG"


class SignalType(StrEnum):
    BREAKOUT = "BREAKOUT"
    PULLBACK = "PULLBACK"


class KillSwitchClosePolicy(StrEnum):
    FREEZE = "FREEZE"
    CLOSE_AT_NEXT_OPEN = "CLOSE_AT_NEXT_OPEN"


class SchedulerRunStatus(StrEnum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"
