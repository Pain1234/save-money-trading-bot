"""Process-wide wiring state shared between runner and FastAPI."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from paper_trading.lock import AdvisoryLock


@dataclass
class PaperTradingAppState:
    market_data_ready: Callable[[], bool] = field(default=lambda: False)
    advisory_lock: AdvisoryLock | None = None
    scheduler_active: bool = False


_state = PaperTradingAppState()


def get_app_state() -> PaperTradingAppState:
    return _state


def configure_app_state(
    *,
    market_data_ready: Callable[[], bool] | None = None,
    advisory_lock: AdvisoryLock | None = None,
    scheduler_active: bool | None = None,
) -> None:
    global _state
    if market_data_ready is not None:
        _state.market_data_ready = market_data_ready
    if advisory_lock is not None:
        _state.advisory_lock = advisory_lock
    if scheduler_active is not None:
        _state.scheduler_active = scheduler_active


def reset_app_state() -> None:
    global _state
    _state = PaperTradingAppState()
