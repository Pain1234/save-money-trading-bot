#!/usr/bin/env python3
# ruff: noqa: E402
"""Independent paper trading state verification."""

from __future__ import annotations

import argparse
import os
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services"))
sys.path.insert(0, str(ROOT))

from paper_trading.repository import PaperTradingRepository
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from tests.paper_trading.soak.helpers import assert_soak_invariants


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
        with engine.connect() as conn:
            head = conn.execute(
                text("SELECT version_num FROM alembic_version LIMIT 1")
            ).scalar_one_or_none()
        fill_keys = [f.deterministic_fill_key for f in repo.list_all_fills()]
        dup_fills = [k for k, c in Counter(fill_keys).items() if c > 1]
        if dup_fills:
            issues.append(f"duplicate fill keys: {len(dup_fills)}")
        wallet = repo.get_wallet()
        if wallet is None:
            issues.append("wallet missing")
        runtime = repo.get_runtime_state()
        if runtime is None:
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
    args = parser.parse_args()
    database_url = _resolve_database_url(args.database_url_env)
    result = verify(database_url)
    print(result)
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
