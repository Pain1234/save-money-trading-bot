"""Validated configuration for the paper trading orchestrator."""

from __future__ import annotations

from decimal import Decimal
from typing import Annotated, Self

from pydantic import (
    AnyUrl,
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

from paper_trading.database_url import normalize_postgresql_url, resolve_database_url_from_env
from paper_trading.enums import KillSwitchClosePolicy

ALLOWED_SYMBOLS: frozenset[str] = frozenset({"BTC", "ETH", "SOL"})
DEFAULT_SYMBOLS: tuple[str, ...] = ("BTC", "ETH", "SOL")
POSTGRESQL_BIGINT_MIN = -(2**63)
POSTGRESQL_BIGINT_MAX = 2**63 - 1


class PaperTradingConfig(BaseModel):
    """Paper trading orchestrator configuration (Phases 1–3 scope)."""

    model_config = ConfigDict(frozen=True)

    database_url: Annotated[AnyUrl, Field(description="PostgreSQL connection URL")]
    paper_initial_equity: Decimal = Field(default=Decimal("100000"), gt=0)
    paper_fee_rate: Decimal = Field(default=Decimal("0.0005"), ge=0, le=Decimal("0.01"))
    paper_slippage_bps: Decimal = Field(default=Decimal("5"), ge=0, le=Decimal("100"))
    paper_max_leverage: Decimal = Field(default=Decimal("2"), gt=0, le=Decimal("2"))
    evaluation_delay_seconds: int = Field(default=5, ge=0)
    fill_delay_seconds: int = Field(default=0, ge=0)
    heartbeat_interval_seconds: int = Field(default=30, gt=0)
    stale_runtime_threshold_seconds: int = Field(default=300, gt=0)
    scheduler_enabled: bool = True
    control_api_enabled: bool = False
    control_api_localhost_only: bool = False
    paper_production_mode: bool = False
    control_api_rate_limit_per_minute: int = Field(default=60, gt=0)
    advisory_lock_id: int = Field(default=987654321)
    kill_switch_close_policy: KillSwitchClosePolicy = KillSwitchClosePolicy.FREEZE
    funding_enabled: bool = False
    symbols: tuple[str, ...] = DEFAULT_SYMBOLS

    @field_validator("database_url", mode="before")
    @classmethod
    def normalize_database_url(cls, value: object) -> object:
        if isinstance(value, str):
            return normalize_postgresql_url(value)
        return value

    @field_validator("database_url")
    @classmethod
    def validate_postgresql_url(cls, value: AnyUrl) -> AnyUrl:
        scheme = value.scheme.split("+", maxsplit=1)[0]
        if scheme not in {"postgresql", "postgres"}:
            raise ValueError("database_url must use a PostgreSQL scheme")
        return value

    @field_validator("symbols")
    @classmethod
    def validate_symbols(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if len(value) != len(set(value)):
            raise ValueError("symbols must not contain duplicates")
        unknown = set(value) - ALLOWED_SYMBOLS
        if unknown:
            raise ValueError(f"unsupported symbols: {sorted(unknown)}")
        return value

    @field_validator("advisory_lock_id")
    @classmethod
    def validate_advisory_lock_id(cls, value: int) -> int:
        if not POSTGRESQL_BIGINT_MIN <= value <= POSTGRESQL_BIGINT_MAX:
            raise ValueError("advisory_lock_id must fit PostgreSQL BIGINT")
        return value

    @field_validator("kill_switch_close_policy")
    @classmethod
    def validate_kill_switch_close_policy(
        cls, value: KillSwitchClosePolicy
    ) -> KillSwitchClosePolicy:
        if value == KillSwitchClosePolicy.CLOSE_AT_NEXT_OPEN:
            raise ValueError(
                "CLOSE_AT_NEXT_OPEN is reserved for a future execution version; "
                "paper trading V1 supports KillSwitchClosePolicy.FREEZE only"
            )
        return value

    @model_validator(mode="after")
    def validate_stale_threshold(self) -> Self:
        if self.stale_runtime_threshold_seconds <= self.heartbeat_interval_seconds:
            raise ValueError(
                "stale_runtime_threshold_seconds must be greater than heartbeat_interval_seconds"
            )
        return self

    @model_validator(mode="after")
    def validate_funding_disabled(self) -> Self:
        if self.funding_enabled:
            raise ValueError(
                "funding_enabled=True is not supported in paper trading V1; "
                "perpetual funding processing is not implemented"
            )
        return self

    @classmethod
    def from_env(cls, **overrides: object) -> PaperTradingConfig:
        """Build config from environment with optional overrides (for tests)."""
        import os

        data: dict[str, object] = {
            "database_url": resolve_database_url_from_env(
                "PAPER_TRADING_DATABASE_URL",
                default="postgresql://postgres:postgres@localhost:5432/paper_trading_test",
            ),
            "paper_initial_equity": Decimal(
                os.environ.get("PAPER_INITIAL_EQUITY", "100000")
            ),
            "paper_fee_rate": Decimal(os.environ.get("PAPER_FEE_RATE", "0.0005")),
            "paper_slippage_bps": Decimal(os.environ.get("PAPER_SLIPPAGE_BPS", "5")),
            "paper_max_leverage": Decimal(os.environ.get("PAPER_MAX_LEVERAGE", "2")),
            "evaluation_delay_seconds": int(
                os.environ.get("PAPER_EVALUATION_DELAY_SECONDS", "5")
            ),
            "fill_delay_seconds": int(os.environ.get("PAPER_FILL_DELAY_SECONDS", "0")),
            "heartbeat_interval_seconds": int(
                os.environ.get("PAPER_HEARTBEAT_INTERVAL_SECONDS", "30")
            ),
            "stale_runtime_threshold_seconds": int(
                os.environ.get("PAPER_STALE_RUNTIME_THRESHOLD_SECONDS", "300")
            ),
            "scheduler_enabled": os.environ.get("PAPER_SCHEDULER_ENABLED", "true").lower()
            in {"1", "true", "yes"},
            "control_api_enabled": os.environ.get("PAPER_CONTROL_API_ENABLED", "false").lower()
            in {"1", "true", "yes"},
            "control_api_localhost_only": os.environ.get(
                "PAPER_CONTROL_API_LOCALHOST_ONLY", "false"
            ).lower()
            in {"1", "true", "yes"},
            "paper_production_mode": os.environ.get("PAPER_PRODUCTION_MODE", "false").lower()
            in {"1", "true", "yes"},
            "control_api_rate_limit_per_minute": int(
                os.environ.get("PAPER_CONTROL_API_RATE_LIMIT_PER_MINUTE", "60")
            ),
            "advisory_lock_id": int(os.environ.get("PAPER_ADVISORY_LOCK_ID", "987654321")),
            "kill_switch_close_policy": os.environ.get(
                "PAPER_KILL_SWITCH_CLOSE_POLICY", "FREEZE"
            ),
            "funding_enabled": os.environ.get("PAPER_FUNDING_ENABLED", "false").lower()
            in {"1", "true", "yes"},
        }
        data.update(overrides)
        return cls.model_validate(data)
