#!/usr/bin/env python3
"""Measure SQLAlchemy cursor-listener overhead (P2.5 / Issue #96).

Compares in-process ``SELECT 1`` timing with and without
``attach_engine_query_metrics`` / ``detach_engine_query_metrics``.

Usage:
    export PAPER_TRADING_DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/paper_trading_test
    export PYTHONPATH=services
    python scripts/measure_instrumentation_overhead.py
    python scripts/measure_instrumentation_overhead.py --loops 1000 --json
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import time
from typing import Any

from sqlalchemy import create_engine, text

from paper_trading.perf_observability import (
    RequestPerfMetrics,
    attach_engine_query_metrics,
    detach_engine_query_metrics,
)


def _pct(values: list[float], pct: float) -> float:
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, int(round((pct / 100.0) * (len(ordered) - 1)))))
    return ordered[index]


def _per_query_samples(engine: Any, *, loops: int, with_listeners: bool) -> list[float]:
    samples: list[float] = []
    metrics = RequestPerfMetrics(correlation_id="bench")
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
        listeners = (
            attach_engine_query_metrics(engine, metrics) if with_listeners else None
        )
        for _ in range(loops):
            started = time.perf_counter()
            conn.execute(text("SELECT 1"))
            samples.append((time.perf_counter() - started) * 1_000_000.0)
        if listeners is not None:
            detach_engine_query_metrics(engine, *listeners)
    return samples


def _attach_detach_samples(engine: Any, *, loops: int) -> list[float]:
    samples: list[float] = []
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
        for _ in range(loops):
            metrics = RequestPerfMetrics(correlation_id="bench")
            started = time.perf_counter()
            listeners = attach_engine_query_metrics(engine, metrics)
            detach_engine_query_metrics(engine, *listeners)
            samples.append((time.perf_counter() - started) * 1_000_000.0)
    return samples


def build_report(*, database_url: str, loops: int, attach_loops: int) -> dict[str, Any]:
    engine = create_engine(database_url, pool_pre_ping=True)
    without = _per_query_samples(engine, loops=loops, with_listeners=False)
    with_listeners = _per_query_samples(engine, loops=loops, with_listeners=True)
    attach = _attach_detach_samples(engine, loops=attach_loops)
    engine.dispose()

    def summary(samples: list[float]) -> dict[str, float]:
        return {
            "median_us": statistics.median(samples),
            "p95_us": _pct(samples, 95),
            "max_us": max(samples),
            "samples": float(len(samples)),
        }

    without_s = summary(without)
    with_s = summary(with_listeners)
    return {
        "database_url_scheme": database_url.split("://", 1)[0],
        "python": sys.version.split()[0],
        "query_loops": loops,
        "without_listeners_us": without_s,
        "with_listeners_us": with_s,
        "delta_us": {
            "median_us": with_s["median_us"] - without_s["median_us"],
            "p95_us": with_s["p95_us"] - without_s["p95_us"],
        },
        "attach_detach_us": summary(attach),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Measure DB instrumentation overhead")
    parser.add_argument(
        "--database-url",
        default=os.environ.get("PAPER_TRADING_DATABASE_URL"),
        help="SQLAlchemy URL (default: PAPER_TRADING_DATABASE_URL)",
    )
    parser.add_argument("--loops", type=int, default=1000)
    parser.add_argument("--attach-loops", type=int, default=200)
    parser.add_argument("--json", action="store_true", help="Print JSON only")
    args = parser.parse_args(argv)
    if not args.database_url:
        print("ERROR: set PAPER_TRADING_DATABASE_URL or --database-url", file=sys.stderr)
        return 1

    report = build_report(
        database_url=args.database_url,
        loops=args.loops,
        attach_loops=args.attach_loops,
    )
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        d = report["delta_us"]
        a = report["attach_detach_us"]
        print(f"python={report['python']} loops={report['query_loops']}")
        print(
            "query_us without median/p95 "
            f"{report['without_listeners_us']['median_us']:.1f} "
            f"{report['without_listeners_us']['p95_us']:.1f}"
        )
        print(
            "query_us with    median/p95 "
            f"{report['with_listeners_us']['median_us']:.1f} "
            f"{report['with_listeners_us']['p95_us']:.1f}"
        )
        print(f"query_us delta   median/p95 {d['median_us']:.1f} {d['p95_us']:.1f}")
        print(f"attach_detach_us median/p95 {a['median_us']:.1f} {a['p95_us']:.1f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
