#!/usr/bin/env python3
"""Measure read-only API latency baseline for P2.5 (Issue #95).

Usage:
    export PAPER_API_BASE_URL=http://127.0.0.1:8080
    python scripts/measure_dashboard_api_baseline.py --warm-runs 20 --cold-runs 3
    python scripts/measure_dashboard_api_baseline.py \\
        --output docs/operations/dashboard-performance-baseline.json

Measures API latency only (not SSR, Playwright, or DB query plans).
Does not apply optimizations unless --optimization-applied is set.
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any
from urllib.error import URLError
from urllib.request import Request, urlopen

CORE_ENDPOINTS: tuple[tuple[str, str], ...] = (
    ("status", "/api/v1/status"),
    ("wallet", "/api/v1/wallet"),
    ("positions", "/api/v1/positions?limit=50"),
    ("orders", "/api/v1/orders?limit=50"),
    ("fills", "/api/v1/fills?limit=50"),
    ("equity", "/api/v1/equity?limit=100"),
)

OPTIONAL_SUMMARY_ENDPOINT: tuple[str, str] = (
    "dashboard_summary",
    "/api/v1/dashboard-summary",
)

# Status + wallet parallel fetch mirrors pre-#98 dashboard overview.
OVERVIEW_PARALLEL_PATHS: tuple[tuple[str, str], ...] = (
    ("status", "/api/v1/status"),
    ("wallet", "/api/v1/wallet"),
)

# With n=20, p95 index ≈ 0.95*(n-1) ≈ 18 → second-highest order statistic.
DEFAULT_WARM_RUNS = 20
DEFAULT_COLD_RUNS = 3
MIN_RECOMMENDED_WARM_RUNS = 20


def resolve_endpoints(*, include_summary: bool) -> tuple[tuple[str, str], ...]:
    if include_summary:
        return CORE_ENDPOINTS + (OPTIONAL_SUMMARY_ENDPOINT,)
    return CORE_ENDPOINTS


# Backward-compatible alias for unit tests.
DEFAULT_ENDPOINTS = resolve_endpoints(include_summary=False)


@dataclass(frozen=True)
class SampleStats:
    p50_ms: float
    p95_ms: float
    max_ms: float
    samples: int
    response_bytes_p50: int = 0
    response_bytes_max: int = 0


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


def _stats(values: list[float], sizes: list[int] | None = None) -> SampleStats:
    size_list = sizes if sizes is not None else [0] * len(values)
    return SampleStats(
        p50_ms=statistics.median(values),
        p95_ms=_percentile(values, 95),
        max_ms=max(values) if values else 0.0,
        samples=len(values),
        response_bytes_p50=int(statistics.median(size_list)) if size_list else 0,
        response_bytes_max=max(size_list) if size_list else 0,
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


def _fetch_parallel_wall_ms(
    base_url: str,
    paths: tuple[str, ...],
    *,
    cold: bool,
) -> tuple[float, int]:
    """Wall-clock time for concurrent GETs (dashboard overview fan-out)."""
    started = time.perf_counter()
    with ThreadPoolExecutor(max_workers=len(paths)) as pool:
        futures = [pool.submit(_fetch_ms, base_url, path, cold=cold) for path in paths]
        results = [future.result() for future in futures]
    elapsed_ms = (time.perf_counter() - started) * 1000.0
    total_bytes = sum(size for _ms, size in results)
    return elapsed_ms, total_bytes


def measure_endpoint(
    base_url: str,
    name: str,
    path: str,
    *,
    cold_runs: int,
    warm_runs: int,
) -> EndpointBaseline:
    cold_values: list[float] = []
    cold_sizes: list[int] = []
    warm_values: list[float] = []
    warm_sizes: list[int] = []
    for _ in range(cold_runs):
        ms, size = _fetch_ms(base_url, path, cold=True)
        cold_values.append(ms)
        cold_sizes.append(size)
        time.sleep(0.05)
    for _ in range(warm_runs):
        ms, size = _fetch_ms(base_url, path, cold=False)
        warm_values.append(ms)
        warm_sizes.append(size)
        time.sleep(0.02)
    return EndpointBaseline(
        name=name,
        path=path,
        cold=_stats(cold_values, cold_sizes) if cold_values else None,
        warm=_stats(warm_values, warm_sizes),
    )


def measure_parallel_overview(
    base_url: str,
    *,
    cold_runs: int,
    warm_runs: int,
) -> EndpointBaseline:
    paths = tuple(path for _name, path in OVERVIEW_PARALLEL_PATHS)
    cold_values: list[float] = []
    cold_sizes: list[int] = []
    warm_values: list[float] = []
    warm_sizes: list[int] = []
    for _ in range(cold_runs):
        ms, size = _fetch_parallel_wall_ms(base_url, paths, cold=True)
        cold_values.append(ms)
        cold_sizes.append(size)
        time.sleep(0.05)
    for _ in range(warm_runs):
        ms, size = _fetch_parallel_wall_ms(base_url, paths, cold=False)
        warm_values.append(ms)
        warm_sizes.append(size)
        time.sleep(0.02)
    return EndpointBaseline(
        name="overview_parallel_status_wallet",
        path="+".join(paths),
        cold=_stats(cold_values, cold_sizes) if cold_values else None,
        warm=_stats(warm_values, warm_sizes),
    )


def build_report(
    *,
    base_url: str,
    endpoints: tuple[tuple[str, str], ...],
    cold_runs: int,
    warm_runs: int,
    include_summary: bool = False,
    optimization_applied: bool = False,
    include_parallel_overview: bool = True,
) -> dict[str, Any]:
    measured = [
        asdict(
            measure_endpoint(base_url, name, path, cold_runs=cold_runs, warm_runs=warm_runs)
        )
        for name, path in endpoints
    ]
    if include_parallel_overview:
        measured.insert(
            0,
            asdict(
                measure_parallel_overview(
                    base_url,
                    cold_runs=cold_runs,
                    warm_runs=warm_runs,
                )
            ),
        )
    p95_note = (
        f"With warm_runs={warm_runs}, p95 is an order-statistic estimate "
        f"(index round(0.95*(n-1))). Prefer n>={MIN_RECOMMENDED_WARM_RUNS}."
    )
    return {
        "generated_at": datetime.now(tz=UTC).isoformat(),
        "base_url": base_url,
        "environment_notes": {
            "railway_region": os.environ.get("RAILWAY_REGION", "local/unset"),
            "railway_resources": os.environ.get("RAILWAY_RESOURCES", "unset"),
            "python": sys.version.split()[0],
        },
        "methodology": {
            "cold_runs": cold_runs,
            "warm_runs": warm_runs,
            "optimization_applied": optimization_applied,
            "include_dashboard_summary": include_summary,
            "include_parallel_overview": include_parallel_overview,
            "measured_against": os.environ.get("P2_BASELINE_GIT_REF", "unspecified"),
            "p95_interpretation": p95_note,
            "overview_metric": (
                "overview_parallel_status_wallet = wall-clock of concurrent "
                "GET /status + GET /wallet per iteration (not max of separate p95s)"
            ),
            "out_of_scope": [
                "Next.js SSR / dashboard page timing",
                "Playwright login→route flows (Issue #102)",
                "DB query_count / db_ms (Issue #96 instrumentation)",
                "EXPLAIN ANALYZE / index audit (Issue #101)",
                "Railway CPU/RAM resource counters (record in environment_notes)",
            ],
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
    parser.add_argument("--cold-runs", type=int, default=DEFAULT_COLD_RUNS)
    parser.add_argument("--warm-runs", type=int, default=DEFAULT_WARM_RUNS)
    parser.add_argument(
        "--output",
        help="Write JSON report to this path (default: stdout only)",
    )
    parser.add_argument(
        "--include-summary",
        action="store_true",
        help="Also measure /api/v1/dashboard-summary (optional until Issue #98)",
    )
    parser.add_argument(
        "--optimization-applied",
        action="store_true",
        help="Mark report as post-optimization (after stack merge)",
    )
    parser.add_argument(
        "--skip-parallel-overview",
        action="store_true",
        help="Skip concurrent status+wallet overview wall-clock metric",
    )
    args = parser.parse_args(argv)

    if args.warm_runs < MIN_RECOMMENDED_WARM_RUNS:
        print(
            f"WARNING: warm_runs={args.warm_runs} makes p95 nearly equal to max; "
            f"prefer >={MIN_RECOMMENDED_WARM_RUNS}",
            file=sys.stderr,
        )

    endpoints = resolve_endpoints(include_summary=args.include_summary)

    try:
        report = build_report(
            base_url=args.base_url,
            endpoints=endpoints,
            cold_runs=args.cold_runs,
            warm_runs=args.warm_runs,
            include_summary=args.include_summary,
            optimization_applied=args.optimization_applied,
            include_parallel_overview=not args.skip_parallel_overview,
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
