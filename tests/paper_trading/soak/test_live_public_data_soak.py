"""Optional bounded live public Hyperliquid testnet soak."""

from __future__ import annotations

import asyncio
import os

import pytest

pytestmark = pytest.mark.live


@pytest.mark.asyncio
async def test_live_public_data_soak() -> None:
    if os.environ.get("RUN_PAPER_LIVE_SOAK", "0") != "1":
        pytest.skip("RUN_PAPER_LIVE_SOAK not enabled")
    if os.environ.get("HYPERLIQUID_NETWORK", "") != "testnet":
        pytest.skip("HYPERLIQUID_NETWORK must be testnet")

    max_seconds = min(int(os.environ.get("PAPER_LIVE_SOAK_SECONDS", "300")), 600)
    assert max_seconds > 0

    from alembic.config import Config
    from paper_trading.application import PaperTradingApplication
    from paper_trading.enums import RuntimeStatus
    from paper_trading.service_config import PaperServiceConfig

    db_url = os.environ.get("PAPER_TRADING_DATABASE_URL")
    if not db_url:
        pytest.skip("PAPER_TRADING_DATABASE_URL required for live soak")

    root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
    alembic_cfg = Config(os.path.join(root, "alembic.ini"))
    alembic_cfg.set_main_option("sqlalchemy.url", db_url)

    config = PaperServiceConfig.from_env(database_url=db_url)
    app = PaperTradingApplication(config=config, alembic_config=alembic_cfg)
    await app.start()
    try:
        await asyncio.sleep(max_seconds)
        runtime = app.repository.get_runtime_state()
        assert runtime is not None
        assert runtime.status in {RuntimeStatus.READY, RuntimeStatus.DEGRADED}
        assert app.market_data_ready() is True
        orphans = app.repository.get_running_scheduler_runs()
        assert orphans == ()
    finally:
        await app.stop()
