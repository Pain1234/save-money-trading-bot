# ruff: noqa: E402
"""Tests for immutable core engine version metadata."""

from __future__ import annotations

import pytest
from backtester.core_metadata import (
    CORE_ENGINE_METADATA,
    AccountingModel,
    AuditStatus,
    CoreEngineMetadata,
)
from backtester.engine import BacktestEngine
from backtester.models import BacktestConfig
from pydantic import ValidationError

from tests.backtester.conftest import make_bundle, make_config


def test_core_engine_metadata_canonical_values() -> None:
    meta = CORE_ENGINE_METADATA
    assert meta.strategy_version == "1.0"
    assert meta.risk_version == "1.0"
    assert meta.backtester_version == "1.0"
    assert meta.accounting_model == AccountingModel.PERPETUAL_MARGIN
    assert meta.audit_status == AuditStatus.PAPER_TRADING_APPROVED


def test_core_engine_metadata_is_frozen() -> None:
    with pytest.raises(ValidationError):
        CORE_ENGINE_METADATA.strategy_version = "2.0"  # type: ignore[misc]


def test_backtest_config_includes_core_metadata_defaults() -> None:
    config = BacktestConfig()
    assert config.core_metadata == CORE_ENGINE_METADATA
    assert config.core_metadata.strategy_version == "1.0"
    assert config.core_metadata.risk_version == "1.0"
    assert config.core_metadata.backtester_version == "1.0"
    assert config.core_metadata.accounting_model == "PERPETUAL_MARGIN"
    assert config.core_metadata.audit_status == "PAPER_TRADING_APPROVED"


def test_backtest_result_propagates_core_metadata() -> None:
    config = make_config(("BTC",))
    result = BacktestEngine().run(make_bundle("BTC"), config)
    assert result.core_metadata == config.core_metadata
    assert result.core_metadata == CORE_ENGINE_METADATA


def test_core_engine_metadata_equality_and_copy() -> None:
    assert CoreEngineMetadata() == CORE_ENGINE_METADATA
    assert CoreEngineMetadata().model_copy() == CORE_ENGINE_METADATA
