#!/usr/bin/env python3
# ruff: noqa: E402
"""Independent paper trading state verification."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services"))
sys.path.insert(0, str(ROOT))

from paper_trading.repository import PaperTradingRepository
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from tests.paper_trading.soak.helpers import assert_soak_invariants, verify_accounting_independent


def _resolve_database_url(env_name: str) -> str:
    url = os.environ.get(env_name)
    if not url:
        raise SystemExit(f"missing environment variable {env_name}")
    return url


def verify(database_url: str) -> dict[str, object]:
    engine = create_engine(database_url, pool_pre_ping=True)
    issues: list[str] = []
    with Session(engine) as session:
        repo = PaperTradingRepository(session)
        try:
            assert_soak_invariants(repo)
        except AssertionError as exc:
            issues.append(str(exc))
        issues.extend(verify_accounting_independent(repo))
        with engine.connect() as conn:
            head = conn.execute(
                text("SELECT version_num FROM alembic_version LIMIT 1")
            ).scalar_one_or_none()
        fill_keys = [f.deterministic_fill_key for f in repo.list_all_fills()]
        if len(fill_keys) != len(set(fill_keys)):
            issues.append("duplicate deterministic fill keys")
        if repo.get_wallet() is None:
            issues.append("wallet missing")
        if repo.get_runtime_state() is None:
            issues.append("runtime missing")
    engine.dispose()
    return {
        "ok": not issues,
        "issues": issues,
        "migration": head,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify paper trading DB invariants")
    parser.add_argument(
        "--database-url-env",
        default="PAPER_TRADING_DATABASE_URL",
        help="Environment variable containing PostgreSQL URL",
    )
    parser.add_argument("--json", action="store_true", help="emit JSON report")
    args = parser.parse_args()
    database_url = _resolve_database_url(args.database_url_env)
    result = verify(database_url)
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(result)
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
