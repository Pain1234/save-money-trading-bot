"""Standalone read-only API entrypoint for Railway."""

from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
    host = os.environ.get("PAPER_API_HOST", "0.0.0.0")
    port = int(os.environ.get("PAPER_API_PORT", "8080"))
    if not os.environ.get("PAPER_TRADING_DATABASE_URL"):
        raise SystemExit("PAPER_TRADING_DATABASE_URL is required")
    if os.environ.get("PAPER_CONTROL_API_ENABLED", "false").lower() in {"1", "true", "yes"}:
        raise SystemExit("PAPER_CONTROL_API_ENABLED must be false for read-only API")

    from paper_trading.config import PaperTradingConfig
    from paper_trading.database_identity import (
        inspect_database_identity,
        log_database_identity,
    )
    from paper_trading.db.session import create_db_engine

    config = PaperTradingConfig.from_env()
    engine = create_db_engine(
        str(config.database_url),
        application_name="paper-readonly-api",
    )
    try:
        identity = inspect_database_identity(engine, service_role="readonly-api")
        log_database_identity(logger, identity)
    finally:
        engine.dispose()

    import uvicorn

    logger.info("starting_readonly_api host=%s port=%s", host, port)
    uvicorn.run(
        "paper_trading.readonly_api:app",
        host=host,
        port=port,
        log_level="info",
    )


if __name__ == "__main__":
    main()
