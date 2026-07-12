"""Runtime recovery startup tests."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from paper_trading.config import PaperTradingConfig
from paper_trading.enums import RuntimeStatus
from paper_trading.lock import InMemoryAdvisoryLock
from paper_trading.recovery import RecoveryResult
from paper_trading.runtime import RuntimeService
from paper_trading.transitions import validate_runtime_transition

from tests.paper_trading.conftest_execution import utc_dt


def test_recover_on_startup_delegates_to_recovery_module() -> None:
    repo = MagicMock()
    config = PaperTradingConfig.from_env(
        database_url="postgresql://postgres:postgres@localhost:5432/paper_trading_test"
    )
    lock = InMemoryAdvisoryLock("test")
    lock.try_acquire()
    expected = RecoveryResult(
        success=True,
        final_status=RuntimeStatus.READY,
        issues=(),
        repairs_applied=(),
        entry_readiness=True,
    )
    with patch("paper_trading.recovery.recover_on_startup", return_value=expected) as mocked:
        service = RuntimeService(repo, clock=MagicMock(now=lambda: utc_dt(2024, 1, 16)))
        result = service.recover_on_startup(
            config,
            lock,
            market_data_ready=True,
        )
    mocked.assert_called_once()
    assert result.final_status == RuntimeStatus.READY


def test_runtime_transition_starting_to_recovering_valid() -> None:
    validate_runtime_transition(RuntimeStatus.STARTING, RuntimeStatus.RECOVERING)


def test_runtime_transition_degraded_to_recovering_valid() -> None:
    validate_runtime_transition(RuntimeStatus.DEGRADED, RuntimeStatus.RECOVERING)
