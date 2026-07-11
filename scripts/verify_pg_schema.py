"""Verify PostgreSQL schema for paper trading gate checks."""

from __future__ import annotations

import os
import sys

from sqlalchemy import create_engine, inspect, text

URL = os.environ.get("PAPER_TRADING_DATABASE_URL")
if not URL:
    print("PAPER_TRADING_DATABASE_URL not set", file=sys.stderr)
    sys.exit(1)

EXPECTED_TABLES = {
    "audit_events",
    "funding_events",
    "paper_fills",
    "paper_orders",
    "paper_positions",
    "paper_wallet",
    "portfolio_snapshots",
    "position_stop_history",
    "runtime_state",
    "scheduler_runs",
    "strategy_evaluations",
    "trade_intents",
}


def main() -> None:
    engine = create_engine(URL)
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    missing = EXPECTED_TABLES - tables
    if missing:
        print(f"FAIL missing tables: {sorted(missing)}")
        sys.exit(1)
    print(f"OK tables ({len(EXPECTED_TABLES)}): {sorted(tables & EXPECTED_TABLES)}")

    with engine.connect() as conn:
        version = conn.execute(text("SELECT version()")).scalar()
        print(f"OK version: {str(version).split(',')[0]}")

        floats = conn.execute(
            text(
                """
                SELECT table_name, column_name, data_type
                FROM information_schema.columns
                WHERE table_schema = 'public'
                  AND data_type IN ('real', 'double precision')
                ORDER BY 1, 2
                """
            )
        ).fetchall()
        if floats:
            print(f"FAIL float columns: {floats}")
            sys.exit(1)
        print("OK no float/double columns")

        entry_atr = conn.execute(
            text(
                """
                SELECT column_name, is_nullable, data_type, numeric_precision, numeric_scale
                FROM information_schema.columns
                WHERE table_name = 'paper_positions' AND column_name = 'entry_atr14'
                """
            )
        ).fetchone()
        assert entry_atr is not None and entry_atr[1] == "NO"
        col_type = f"{entry_atr[2]}({entry_atr[3]},{entry_atr[4]})"
        print(f"OK paper_positions.entry_atr14 {col_type} NOT NULL")

        snap_key = conn.execute(
            text(
                """
                SELECT 1 FROM pg_indexes
                WHERE tablename = 'portfolio_snapshots'
                  AND indexdef ILIKE '%idempotency_key%'
                  AND indexdef ILIKE '%UNIQUE%'
                """
            )
        ).fetchone()
        if not snap_key:
            print("FAIL portfolio_snapshots.idempotency_key unique index")
            sys.exit(1)
        print("OK portfolio_snapshots.idempotency_key UNIQUE")

        partial = conn.execute(
            text(
                """
                SELECT indexname, indexdef FROM pg_indexes
                WHERE tablename = 'paper_positions'
                  AND indexdef ILIKE '%OPEN%'
                """
            )
        ).fetchall()
        if not partial:
            print("FAIL partial unique index on open positions")
            sys.exit(1)
        print(f"OK partial position index: {partial[0][0]}")

        fill_seq = conn.execute(
            text(
                """
                SELECT column_name FROM information_schema.columns
                WHERE table_name = 'paper_fills' AND column_name = 'fill_sequence'
                """
            )
        ).fetchone()
        if not fill_seq:
            print("FAIL paper_fills.fill_sequence missing")
            sys.exit(1)
        print("OK paper_fills.fill_sequence")

        wallet = conn.execute(text("SELECT 1 FROM paper_wallet LIMIT 1")).fetchone()
        runtime = conn.execute(text("SELECT 1 FROM runtime_state LIMIT 1")).fetchone()
        if not wallet or not runtime:
            print("FAIL seed rows missing")
            sys.exit(1)
        print("OK seed rows for paper_wallet and runtime_state")

        checks = conn.execute(
            text(
                """
                SELECT conname FROM pg_constraint
                WHERE contype = 'c' AND conrelid::regclass::text LIKE 'paper_%'
                """
            )
        ).fetchall()
        print(f"OK check constraints on paper_* tables: {len(checks)}")

    print("SCHEMA VERIFICATION PASSED")


if __name__ == "__main__":
    main()
