#!/usr/bin/env python3
# ruff: noqa: E402
"""Run deterministic accelerated paper trading soak and verify state."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services"))
sys.path.insert(0, str(ROOT))

from alembic import command
from alembic.config import Config
from paper_trading.repository import PaperTradingRepository
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from tests.paper_trading.e2e.helpers import (
    PaperE2EHarness,
    historical_to_strategy_bundle,
    paper_config_from_env,
)
from tests.paper_trading.soak.helpers import (
    SoakMetrics,
    assert_soak_invariants,
    generate_soak_bundle,
)


def _database_url(env_name: str) -> str:
    url = os.environ.get(env_name)
    if not url:
        raise SystemExit(f"missing environment variable {env_name}")
    return url


def run_soak(*, database_url: str, days: int, seed: int) -> SoakMetrics:
    cfg = Config(str(ROOT / "alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", database_url)
    command.upgrade(cfg, "head")
    engine = create_engine(database_url, pool_pre_ping=True)
    started = time.perf_counter()
    with Session(engine) as session:
        repo = PaperTradingRepository(session)
        config = paper_config_from_env(database_url)
        harness = PaperE2EHarness(repo, config)
        harness.set_runtime_ready()
        hist = generate_soak_bundle(days=days, seed=seed)
        stop_updates = 0
        for day_idx in range(60, days, 7):
            for symbol in ("BTC", "ETH", "SOL"):
                dailies = hist.daily[symbol]
                if day_idx >= len(dailies):
                    continue
                strat_bundle, eval_time = historical_to_strategy_bundle(
                    hist, symbol, daily_count=day_idx + 1
                )
                if not strat_bundle.is_usable:
                    continue
                harness.evaluate_at_close(symbol, strat_bundle, eval_time)
                day = dailies[day_idx]
                results = harness.update_trailing(
                    evaluation_time=eval_time,
                    daily_candles={symbol: day},
                    atr_by_symbol={symbol: __import__("decimal").Decimal("5")},
                )
                stop_updates += sum(1 for r in results if r.updated)
        assert_soak_invariants(repo)
        session.commit()
        counts = harness.counts()
    elapsed = time.perf_counter() - started
    engine.dispose()
    return SoakMetrics(
        days=days,
        evaluations=counts.evaluations,
        intents=counts.intents,
        fills=counts.fills,
        stop_updates=stop_updates,
        audit_events=counts.audit_events,
        elapsed_seconds=elapsed,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Deterministic paper trading soak runner")
    parser.add_argument("--database-url-env", default="PAPER_TRADING_DATABASE_URL")
    parser.add_argument("--days", type=int, default=365)
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--json-out", default="")
    args = parser.parse_args()
    database_url = _database_url(args.database_url_env)
    metrics = run_soak(database_url=database_url, days=args.days, seed=args.seed)
    report = {
        "ok": True,
        "days": metrics.days,
        "evaluations": metrics.evaluations,
        "intents": metrics.intents,
        "fills": metrics.fills,
        "stop_updates": metrics.stop_updates,
        "audit_events": metrics.audit_events,
        "elapsed_seconds": round(metrics.elapsed_seconds, 3),
        "seed": args.seed,
    }
    text = json.dumps(report, indent=2)
    print(text)
    if args.json_out:
        Path(args.json_out).write_text(text, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
