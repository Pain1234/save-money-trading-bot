#!/usr/bin/env python3
"""Run independent wallet reconciliation against the configured paper trading database."""

from __future__ import annotations

import sys

from paper_trading.accounting_verification import verify_accounting_independent
from paper_trading.config import PaperTradingConfig
from paper_trading.db.session import create_db_engine, create_session_factory
from paper_trading.repository import PaperTradingRepository


def main() -> int:
    config = PaperTradingConfig.from_env()
    engine = create_db_engine(str(config.database_url))
    session = create_session_factory(engine)()
    try:
        repo = PaperTradingRepository(session)
        issues = verify_accounting_independent(
            repo,
            initial_cash=config.paper_initial_equity,
        )
        if issues:
            print("RECONCILIATION FAILED:")
            for issue in issues:
                print(f"  - {issue}")
            return 1
        print("RECONCILIATION OK")
        return 0
    finally:
        session.close()
        engine.dispose()


if __name__ == "__main__":
    sys.exit(main())
