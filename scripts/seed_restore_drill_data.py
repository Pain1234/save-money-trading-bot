#!/usr/bin/env python3
"""Seed committed paper-trading rows for local restore drill (Issue #11)."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services"))
sys.path.insert(0, str(ROOT))

from alembic import command
from alembic.config import Config
from paper_trading.database_url import resolve_database_url_from_env
from paper_trading.enums import PaperPositionStatus
from paper_trading.repository import PaperTradingRepository
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from scripts.restore_drill_snapshot import assert_business_data_present, capture_snapshot
from tests.paper_trading.conftest import _ensure_postgres_test_env, _reset_postgres_trading_state
from tests.paper_trading.e2e.helpers import (
    PaperE2EHarness,
    build_extended_lifecycle_bundle,
    candle_at,
    fill_context_for_bundle,
    historical_to_strategy_bundle,
    paper_config_from_env,
)


def _run_committed_trade_lifecycle(session: Session, database_url: str) -> None:
    config = paper_config_from_env(database_url)
    repo = PaperTradingRepository(session)
    harness = PaperE2EHarness(repo, config)
    harness.set_runtime_ready()

    symbol = "BTC"
    hist = build_extended_lifecycle_bundle(symbol)
    signal_idx = 29
    fill_idx = 30
    exit_idx = 35

    bundle, eval_time = historical_to_strategy_bundle(hist, symbol, daily_count=signal_idx + 1)
    first_eval = harness.evaluate_at_close(symbol, bundle, eval_time)
    if not first_eval.created or first_eval.intent is None:
        raise RuntimeError("expected trade intent to be created")

    fill_candle = candle_at(hist, symbol, fill_idx)
    fill_time = fill_candle.open_time
    harness.fill_at_open(
        process_time=fill_time,
        symbol_contexts={symbol: fill_context_for_bundle(bundle, eval_time, fill_candle)},
    )
    position = harness.repo.get_open_position_for_symbol(symbol)
    if position is None or position.status != PaperPositionStatus.OPEN:
        raise RuntimeError("expected open position after entry fill")

    for day_idx in range(fill_idx + 1, exit_idx):
        day = candle_at(hist, symbol, day_idx)
        eval_bundle, day_eval_time = historical_to_strategy_bundle(
            hist, symbol, daily_count=day_idx + 1
        )
        harness.evaluate_at_close(symbol, eval_bundle, day_eval_time)
        harness.update_trailing(
            evaluation_time=day_eval_time,
            daily_candles={symbol: day},
            atr_by_symbol={symbol: position.entry_atr14},
        )
        updated = harness.repo.get_open_position_for_symbol(symbol)
        if updated is None:
            raise RuntimeError("position disappeared during trailing updates")
        position = updated

    exit_candle = candle_at(hist, symbol, exit_idx)
    harness.process_stops(
        process_time=exit_candle.open_time,
        daily_candles={symbol: exit_candle},
    )
    if harness.repo.get_open_position_for_symbol(symbol) is not None:
        raise RuntimeError("expected position closed after stop processing")

    session.commit()


def main() -> int:
    _ensure_postgres_test_env()
    database_url = resolve_database_url_from_env("PAPER_TRADING_DATABASE_URL")

    alembic_cfg = Config(str(ROOT / "alembic.ini"))
    alembic_cfg.set_main_option("sqlalchemy.url", database_url)
    command.upgrade(alembic_cfg, "head")

    engine = create_engine(database_url, pool_pre_ping=True)
    _reset_postgres_trading_state(engine)

    session = Session(engine, autoflush=False, expire_on_commit=False)
    try:
        _run_committed_trade_lifecycle(session, database_url)
    finally:
        session.close()
        engine.dispose()

    snapshot = capture_snapshot(database_url)
    issues = assert_business_data_present(snapshot)
    if issues:
        print("Seed verification failed:", file=sys.stderr)
        for issue in issues:
            print(f"  - {issue}", file=sys.stderr)
        return 1

    snapshot_path = ROOT / "restore_drill_snapshot.json"
    snapshot_path.write_text(json.dumps(snapshot, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Seeded committed trade lifecycle; snapshot written to {snapshot_path}")
    print(json.dumps(snapshot, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
