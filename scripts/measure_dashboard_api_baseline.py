#!/usr/bin/env python3
"""Measure read-only API latency baseline for P2.5 (Issue #95).

Usage:
    export PAPER_API_BASE_URL=http://127.0.0.1:8080
    python scripts/measure_dashboard_api_baseline.py --warm-runs 20
    python scripts/measure_dashboard_api_baseline.py \
        --output docs/operations/dashboard-performance-baseline.json

Does not apply optimizations — measurement only.
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import time
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any
from urllib.error import URLError
from urllib.request import Request, urlopen

DEFAULT_ENDPOINTS: tuple[tuple[str, str], ...] = (
    ("status", "/api/v1/status"),
    ("wallet", "/api/v1/wallet"),
    ("positions", "/api/v1/positions?limit=50"),
    ("orders", "/api/v1/orders?limit=50"),
    ("fills", "/api/v1/fills?limit=50"),
    ("equity", "/api/v1/equity?limit=100"),
    ("dashboard_summary", "/api/v1/dashboard-summary"),
)


@dataclass(frozen=True)
class SampleStats:
    p50_ms: float
    p95_ms: float
    max_ms: float
    samples: int


@dataclass(frozen=True)
class EndpointBaseline:
    name: str
    path: str
    cold: SampleStats | None
    warm: SampleStats


def _percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, int(round((pct / 100.0) * (len(ordered) - 1)))))
    return ordered[index]


def _stats(values: list[float]) -> SampleStats:
    return SampleStats(
        p50_ms=statistics.median(values),
        p95_ms=_percentile(values, 95),
        max_ms=max(values),
        samples=len(values),
    )


def _fetch_ms(base_url: str, path: str, *, cold: bool) -> tuple[float, int]:
    url = f"{base_url.rstrip('/')}{path}"
    headers = {"Accept": "application/json"}
    if cold:
        headers["Cache-Control"] = "no-cache"
        headers["Pragma"] = "no-cache"
    started = time.perf_counter()
    request = Request(url, headers=headers, method="GET")
    with urlopen(request, timeout=30) as response:
        body = response.read()
    elapsed_ms = (time.perf_counter() - started) * 1000.0
    return elapsed_ms, len(body)


def measure_endpoint(
    base_url: str,
    name: str,
    path: str,
    *,
    cold_runs: int,
    warm_runs: int,
) -> EndpointBaseline:
    cold_values: list[float] = []
    warm_values: list[float] = []
    for _ in range(cold_runs):
        ms, _size = _fetch_ms(base_url, path, cold=True)
        cold_values.append(ms)
        time.sleep(0.05)
    for _ in range(warm_runs):
        ms, _size = _fetch_ms(base_url, path, cold=False)
        warm_values.append(ms)
        time.sleep(0.02)
    return EndpointBaseline(
        name=name,
        path=path,
        cold=_stats(cold_values) if cold_values else None,
        warm=_stats(warm_values),
    )


def build_report(
    *,
    base_url: str,
    endpoints: tuple[tuple[str, str], ...],
    cold_runs: int,
    warm_runs: int,
) -> dict[str, Any]:
    measured = [
        asdict(
            measure_endpoint(base_url, name, path, cold_runs=cold_runs, warm_runs=warm_runs)
        )
        for name, path in endpoints
    ]
    return {
        "generated_at": datetime.now(tz=UTC).isoformat(),
        "base_url": base_url,
        "environment_notes": {
            "railway_region": os.environ.get("RAILWAY_REGION", "local/unset"),
            "python": sys.version.split()[0],
        },
        "methodology": {
            "cold_runs": cold_runs,
            "warm_runs": warm_runs,
            "optimization_applied": False,
        },
        "p25_budgets_ms": {
            "overview_warm_p95": 1500,
            "status_p95": 250,
            "wallet_p95": 250,
            "table_endpoints_p95": 500,
        },
        "endpoints": measured,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Measure dashboard API performance baseline")
    parser.add_argument(
        "--base-url",
        default=os.environ.get("PAPER_API_BASE_URL", "http://127.0.0.1:8080"),
    )
    parser.add_argument("--cold-runs", type=int, default=3)
    parser.add_argument("--warm-runs", type=int, default=5)
    parser.add_argument(
        "--output",
        help="Write JSON report to this path (default: stdout only)",
    )
    args = parser.parse_args(argv)

    try:
        report = build_report(
            base_url=args.base_url,
            endpoints=DEFAULT_ENDPOINTS,
            cold_runs=args.cold_runs,
            warm_runs=args.warm_runs,
        )
    except URLError as exc:
        print(f"ERROR: could not reach API at {args.base_url}: {exc}", file=sys.stderr)
        return 1

    payload = json.dumps(report, indent=2)
    if args.output:
        output_path = args.output
        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as handle:
            handle.write(payload)
            handle.write("\n")
        print(f"Wrote baseline report to {output_path}")
    else:
        print(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
