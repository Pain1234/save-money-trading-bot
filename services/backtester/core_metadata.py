"""Immutable version and audit metadata for the audited core engine stack."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict


class AccountingModel(StrEnum):
    PERPETUAL_MARGIN = "PERPETUAL_MARGIN"


class AuditStatus(StrEnum):
    PAPER_TRADING_APPROVED = "PAPER_TRADING_APPROVED"


class CoreEngineMetadata(BaseModel):
    """Canonical, immutable metadata for Strategy + Risk + Backtester V1."""

    model_config = ConfigDict(frozen=True)

    strategy_version: str = "1.0"
    risk_version: str = "1.0"
    backtester_version: str = "1.0"
    accounting_model: AccountingModel = AccountingModel.PERPETUAL_MARGIN
    audit_status: AuditStatus = AuditStatus.PAPER_TRADING_APPROVED


CORE_ENGINE_METADATA = CoreEngineMetadata()
