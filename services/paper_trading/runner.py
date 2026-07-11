"""CLI entry point for the paper trading production runner."""

from __future__ import annotations

import asyncio
import logging
import signal
from typing import Any

from paper_trading.application import PaperTradingApplication
from paper_trading.service_config import PaperServiceConfig

logger = logging.getLogger(__name__)


async def run_application(app: PaperTradingApplication) -> None:
    loop = asyncio.get_running_loop()
    stop_event = asyncio.Event()

    def _request_shutdown(*_: Any) -> None:
        logger.info("shutdown_signal_received")
        stop_event.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _request_shutdown)
        except NotImplementedError:
            signal.signal(sig, lambda *_args: _request_shutdown())

    await app.start()
    await stop_event.wait()
    await app.stop()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
    config = PaperServiceConfig.from_env()
    app = PaperTradingApplication(config=config)
    asyncio.run(run_application(app))


if __name__ == "__main__":
    main()
