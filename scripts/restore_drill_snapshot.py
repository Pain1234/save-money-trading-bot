#!/usr/bin/env python3
# ruff: noqa: E402
"""Capture and compare PostgreSQL state for restore drill verification."""

from __future__ import annotations

import argparse
import json
import sys
from decimal import Decimal
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services"))

from paper_trading.database_url import resolve_database_url_from_env
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import Engine

ALLOWED_DRILL_DATABASE = "paper_trading_test"

COUNT_TABLES = (
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
)


def _resolve_database_url(env_name: str) -> str:
    try:
        return resolve_database_url_from_env(env_name)
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc


def _assert_drill_database_safe(engine: Engine) -> None:
    with engine.connect() as conn:
        db_name = conn.execute(text("SELECT current_database()")).scalar_one()
        if str(db_name) != ALLOWED_DRILL_DATABASE:
            raise SystemExit(
                f"Refusing restore drill snapshot on {db_name!r}; "
                f"expected {ALLOWED_DRILL_DATABASE!r}."
            )


def _decimal_default(value: object) -> object:
    if isinstance(value, Decimal):
        return str(value)
    raise TypeError(value)


def capture_snapshot(database_url: str) -> dict[str, Any]:
    engine = create_engine(database_url, pool_pre_ping=True)
    _assert_drill_database_safe(engine)
    try:
        row_counts: dict[str, int] = {}
        with engine.connect() as conn:
            for table in COUNT_TABLES:
                if table not in inspect(engine).get_table_names():
                    row_counts[table] = 0
                    continue
                row_counts[table] = int(
                    conn.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar_one()
                )
            wallet = conn.execute(
                text(
                    """
                    SELECT cash, total_realized_pnl, total_fees, total_funding, total_slippage
                    FROM paper_wallet
                    LIMIT 1
                    """
                )
            ).mappings().one_or_none()
            open_positions = conn.execute(
                text(
                    """
                    SELECT COUNT(*) FROM paper_positions
                    WHERE status = 'OPEN'
                    """
                )
            ).scalar_one()
            closed_positions = conn.execute(
                text(
                    """
                    SELECT COUNT(*) FROM paper_positions
                    WHERE status = 'CLOSED'
                    """
                )
            ).scalar_one()
            fill_count = row_counts.get("paper_fills", 0)
        if wallet is None:
            raise SystemExit("paper_wallet row missing")
        return {
            "row_counts": row_counts,
            "wallet": {key: str(wallet[key]) for key in wallet.keys()},
            "open_positions": int(open_positions),
            "closed_positions": int(closed_positions),
            "fill_count": int(fill_count),
        }
    finally:
        engine.dispose()


def compare_snapshots(expected: dict[str, Any], actual: dict[str, Any]) -> list[str]:
    issues: list[str] = []
    if expected.get("row_counts") != actual.get("row_counts"):
        issues.append(
            f"row_counts mismatch: expected={expected.get('row_counts')} "
            f"actual={actual.get('row_counts')}"
        )
    if expected.get("wallet") != actual.get("wallet"):
        issues.append(
            f"wallet mismatch: expected={expected.get('wallet')} actual={actual.get('wallet')}"
        )
    for key in ("open_positions", "closed_positions", "fill_count"):
        if expected.get(key) != actual.get(key):
            issues.append(f"{key} mismatch: expected={expected.get(key)} actual={actual.get(key)}")
    return issues


def assert_business_data_present(snapshot: dict[str, Any]) -> list[str]:
    issues: list[str] = []
    fills = int(snapshot.get("fill_count", 0))
    if fills < 2:
        issues.append(f"expected at least 2 paper_fills (entry+exit), got {fills}")
    closed = int(snapshot.get("closed_positions", 0))
    if closed < 1:
        issues.append(f"expected at least 1 closed position, got {closed}")
    evaluations = int(snapshot["row_counts"].get("strategy_evaluations", 0))
    if evaluations < 1:
        issues.append(f"expected strategy_evaluations > 0, got {evaluations}")
    cash = Decimal(snapshot["wallet"]["cash"])
    if cash == Decimal("100000"):
        issues.append("wallet cash still at initial seed (100000); no committed trade data")
    return issues


def main() -> int:
    parser = argparse.ArgumentParser(description="Restore drill snapshot capture/compare")
    parser.add_argument(
        "--database-url-env",
        default="PAPER_TRADING_DATABASE_URL",
        help="Environment variable containing PostgreSQL URL",
    )
    parser.add_argument("--write", type=Path, help="Write snapshot JSON to path")
    parser.add_argument("--compare", type=Path, help="Compare current DB to snapshot file")
    parser.add_argument(
        "--require-business-data",
        action="store_true",
        help="Fail if snapshot lacks committed trade lifecycle rows",
    )
    args = parser.parse_args()
    database_url = _resolve_database_url(args.database_url_env)
    snapshot = capture_snapshot(database_url)

    if args.require_business_data:
        issues = assert_business_data_present(snapshot)
        if issues:
            print("BUSINESS DATA CHECK FAILED:", file=sys.stderr)
            for issue in issues:
                print(f"  - {issue}", file=sys.stderr)
            return 1

    if args.write:
        args.write.write_text(
            json.dumps(snapshot, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        print(f"Wrote snapshot to {args.write}")

    if args.compare:
        expected = json.loads(args.compare.read_text(encoding="utf-8"))
        issues = compare_snapshots(expected, snapshot)
        if issues:
            print("SNAPSHOT COMPARE FAILED:")
            for issue in issues:
                print(f"  - {issue}")
            return 1
        print("SNAPSHOT COMPARE OK")

    if not args.write and not args.compare:
        print(json.dumps(snapshot, indent=2, sort_keys=True))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
