"""Production service configuration for the paper trading runner."""

from __future__ import annotations

from typing import Self

from market_data.config import HyperliquidNetwork, HyperliquidPublicConfig
from pydantic import Field

from paper_trading.config import PaperTradingConfig


class PaperServiceConfig(PaperTradingConfig):
    """Extended configuration for the local paper trading production runner."""

    api_enabled: bool = Field(default=False)
    api_host: str = Field(default="127.0.0.1")
    api_port: int = Field(default=8080, ge=1, le=65535)
    market_data_startup_timeout_seconds: int = Field(default=120, gt=0)
    shutdown_timeout_seconds: int = Field(default=30, gt=0)
    hyperliquid_network: HyperliquidNetwork = HyperliquidNetwork.TESTNET

    @classmethod
    def from_env(cls, **overrides: object) -> Self:
        import os

        data = PaperTradingConfig.from_env(**overrides).model_dump()
        data.update(
            {
                "api_enabled": os.environ.get("PAPER_API_ENABLED", "false").lower()
                in {"1", "true", "yes"},
                "api_host": os.environ.get("PAPER_API_HOST", "127.0.0.1"),
                "api_port": int(os.environ.get("PAPER_API_PORT", "8080")),
                "market_data_startup_timeout_seconds": int(
                    os.environ.get("PAPER_MARKET_DATA_STARTUP_TIMEOUT_SECONDS", "120")
                ),
                "shutdown_timeout_seconds": int(
                    os.environ.get("PAPER_SHUTDOWN_TIMEOUT_SECONDS", "30")
                ),
                "hyperliquid_network": os.environ.get("HYPERLIQUID_NETWORK", "testnet"),
            }
        )
        data.update(overrides)
        return cls.model_validate(data)

    def hyperliquid_public_config(self) -> HyperliquidPublicConfig:
        return HyperliquidPublicConfig.for_network(self.hyperliquid_network)
