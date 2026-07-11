"""Tests for runtime state transitions."""

from __future__ import annotations

from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from paper_trading.clock import FixedClock
from paper_trading.enums import RuntimeStatus
from paper_trading.models import RuntimeState
from paper_trading.runtime import RuntimeService
from paper_trading.transitions import InvalidTransitionError, validate_runtime_transition

from tests.paper_trading.conftest_execution import utc_dt


def test_valid_runtime_transitions() -> None:
    validate_runtime_transition(RuntimeStatus.STOPPED, RuntimeStatus.STARTING)
    validate_runtime_transition(RuntimeStatus.STARTING, RuntimeStatus.SYNCING)
    validate_runtime_transition(RuntimeStatus.SYNCING, RuntimeStatus.READY)


def test_invalid_runtime_transition_rejected() -> None:
    with pytest.raises(InvalidTransitionError):
        validate_runtime_transition(RuntimeStatus.STOPPED, RuntimeStatus.READY)


def test_runtime_transition_persists() -> None:
    repo = MagicMock()
    now = utc_dt(2024, 1, 16)
    state = RuntimeState(
        instance_id=uuid4(),
        status=RuntimeStatus.STOPPED,
        heartbeat_at=now,
        version=1,
    )
    repo.get_runtime_state.return_value = state
    repo.update_runtime_state.return_value = state.model_copy(update={"status": RuntimeStatus.STARTING})
    repo.session.begin.return_value.__enter__ = MagicMock(return_value=None)
    repo.session.begin.return_value.__exit__ = MagicMock(return_value=False)
    repo.append_audit_event.return_value = MagicMock()

    service = RuntimeService(repo, clock=FixedClock(now))
    result = service.transition(RuntimeStatus.STARTING)
    assert result.current == RuntimeStatus.STARTING
