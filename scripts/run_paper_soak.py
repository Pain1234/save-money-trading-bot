#!/usr/bin/env python3
# ruff: noqa: E402
"""Run deterministic accelerated paper trading soak and verify state."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services"))
sys.path.insert(0, str(ROOT))

from alembic import command
from alembic.config import Config
from paper_trading.database_url import resolve_database_url_from_env
from paper_trading.repository import PaperTradingRepository
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from tests.paper_trading.e2e.helpers import PaperE2EHarness, paper_config_from_env
from tests.paper_trading.soak.helpers import (
    assert_soak_invariants,
    run_deterministic_soak,
    verify_accounting_independent,
)


def _database_url(env_name: str) -> str:
    try:
        return resolve_database_url_from_env(env_name)
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc


def main() -> int:
    parser = argparse.ArgumentParser(description="Deterministic paper trading soak runner")
    parser.add_argument("--database-url-env", default="PAPER_TRADING_DATABASE_URL")
    parser.add_argument("--days", type=int, default=365)
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--json-out", default="")
    parser.add_argument(
        "--reset-db",
        action="store_true",
        help="downgrade to base and re-apply migrations before soak",
    )
    args = parser.parse_args()
    database_url = _database_url(args.database_url_env)

    cfg = Config(str(ROOT / "alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", database_url)
    if args.reset_db:
        command.downgrade(cfg, "base")
    command.upgrade(cfg, "head")
    engine = create_engine(database_url, pool_pre_ping=True)

    with Session(engine) as session:
        repo = PaperTradingRepository(session)
        config = paper_config_from_env(database_url)
        harness = PaperE2EHarness(repo, config)
        harness.set_runtime_ready()
        report = run_deterministic_soak(harness, days=args.days, seed=args.seed)
        acct_issues = verify_accounting_independent(repo)
        if acct_issues:
            report.errors.extend(acct_issues)
            report.state_verification_ok = False
            report.ok = False
        try:
            assert_soak_invariants(repo)
        except AssertionError as exc:
            report.errors.append(str(exc))
            report.ok = False
        session.commit()

    engine.dispose()
    payload = report.to_dict()
    text = json.dumps(payload, indent=2)
    print(text)
    if args.json_out:
        Path(args.json_out).write_text(text, encoding="utf-8")
    return 0 if report.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
