"""Tests for PaperTradingConfig validation."""

from __future__ import annotations

from decimal import Decimal

import pytest
from paper_trading.config import PaperTradingConfig


def test_defaults_funding_and_control_disabled() -> None:
    config = PaperTradingConfig(
        database_url="postgresql://localhost/paper",
    )
    assert config.funding_enabled is False
    assert config.control_api_enabled is False
    assert config.kill_switch_close_policy.value == "FREEZE"


def test_valid_config() -> None:
    config = PaperTradingConfig(
        database_url="postgresql+psycopg://user:pass@localhost:5432/db",
        paper_initial_equity=Decimal("50000"),
        symbols=("BTC", "ETH", "SOL"),
    )
    assert config.paper_max_leverage == Decimal("2")


def test_rejects_non_postgresql_url() -> None:
    with pytest.raises(ValueError, match="PostgreSQL"):
        PaperTradingConfig(database_url="sqlite:///test.db")


def test_rejects_max_leverage_above_two() -> None:
    with pytest.raises(ValueError):
        PaperTradingConfig(
            database_url="postgresql://localhost/paper",
            paper_max_leverage=Decimal("2.1"),
        )


def test_rejects_unknown_symbol() -> None:
    with pytest.raises(ValueError, match="unsupported symbols"):
        PaperTradingConfig(
            database_url="postgresql://localhost/paper",
            symbols=("BTC", "DOGE"),
        )


def test_rejects_duplicate_symbols() -> None:
    with pytest.raises(ValueError, match="duplicates"):
        PaperTradingConfig(
            database_url="postgresql://localhost/paper",
            symbols=("BTC", "BTC", "ETH"),
        )


def test_rejects_stale_threshold_not_greater_than_heartbeat() -> None:
    with pytest.raises(ValueError, match="stale_runtime_threshold"):
        PaperTradingConfig(
            database_url="postgresql://localhost/paper",
            heartbeat_interval_seconds=60,
            stale_runtime_threshold_seconds=60,
        )


def test_rejects_negative_fee_rate() -> None:
    with pytest.raises(ValueError):
        PaperTradingConfig(
            database_url="postgresql://localhost/paper",
            paper_fee_rate=Decimal("-0.001"),
        )


def test_rejects_close_at_next_open_policy() -> None:
    with pytest.raises(ValueError, match="CLOSE_AT_NEXT_OPEN"):
        PaperTradingConfig(
            database_url="postgresql://localhost/paper",
            kill_switch_close_policy="CLOSE_AT_NEXT_OPEN",
        )


def test_rejects_advisory_lock_out_of_range() -> None:
    with pytest.raises(ValueError, match="BIGINT"):
        PaperTradingConfig(
            database_url="postgresql://localhost/paper",
            advisory_lock_id=2**63,
        )
