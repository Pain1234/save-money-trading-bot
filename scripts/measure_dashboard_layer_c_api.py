#!/usr/bin/env python3
"""Layer C — FastAPI measurement harness for Issue #101.

Reads machine-readable X-Perf-* response headers produced by
``PerformanceLoggingMiddleware`` (Issue #96 / #101).

Status vocabulary per route:
- MEASURED: successful samples with total_ms, db_ms, and query_count headers
- PARTIAL: successful HTTP samples but missing required X-Perf-* headers
- NOT_MEASURED: no successful samples

Usage:
    export PAPER_API_BASE_URL=http://127.0.0.1:8080
    python scripts/measure_dashboard_layer_c_api.py --warm-runs 20 \\
        --output docs/operations/dashboard-layer-c-api.json

Railway note: ``*.railway.internal`` is only reachable from a service in the
same Railway project/environment (probe, temporary job, or ``railway ssh``).
Do not expose the private API publicly to simplify local measurement.
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
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

AUDIT_ROUTES: tuple[tuple[str, str], ...] = (
    ("status", "/api/v1/status"),
    ("dashboard_summary", "/api/v1/dashboard-summary"),
    ("wallet", "/api/v1/wallet"),
    ("positions", "/api/v1/positions?limit=50"),
    ("orders", "/api/v1/orders?limit=50"),
    ("fills", "/api/v1/fills?limit=50"),
    ("equity", "/api/v1/equity?limit=100"),
    ("events", "/api/v1/events?limit=50"),
    ("scheduler_runs", "/api/v1/scheduler-runs?limit=50"),
)

DEFAULT_WARM_RUNS = 20
DEFAULT_WARMUP_RUNS = 3


@dataclass(frozen=True)
class RouteSample:
    status_code: int
    client_total_ms: float
    header_total_ms: float | None
    header_db_ms: float | None
    header_query_count: int | None
    response_bytes: int
    correlation_id: str | None
    payload_json_bytes: int | None = None
    payload_json_share: float | None = None


@dataclass(frozen=True)
class RouteSummary:
    name: str
    path: str
    status: str
    warm_client_p95_ms: float | None
    warm_header_total_p95_ms: float | None
    warm_header_db_p95_ms: float | None
    warm_query_count_p95: float | None
    warm_response_bytes_p50: int | None
    warm_response_bytes_max: int | None
    events_payload_json_bytes_p50: int | None = None
    events_payload_json_share_p50: float | None = None
    note: str = ""


def _percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, int(round((pct / 100.0) * (len(ordered) - 1)))))
    return ordered[index]


def _optional_float(headers: Any, key: str) -> float | None:
    raw = headers.get(key)
    if raw is None:
        return None
    try:
        return float(raw)
    except ValueError:
        return None


def _optional_int(headers: Any, key: str) -> int | None:
    raw = headers.get(key)
    if raw is None:
        return None
    try:
        return int(raw)
    except ValueError:
        return None


def sample_has_required_perf_headers(sample: RouteSample) -> bool:
    """Layer C MEASURED requires total_ms, db_ms, and query_count headers."""
    return (
        sample.header_total_ms is not None
        and sample.header_db_ms is not None
        and sample.header_query_count is not None
    )


def analyze_events_payload(body: bytes) -> tuple[int | None, float | None]:
    """Return (payload_json_bytes, share_of_total) for /events responses."""
    try:
        data = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None, None
    items = data.get("items")
    if not isinstance(items, list):
        return None, None
    payload_bytes = 0
    for item in items:
        if not isinstance(item, dict):
            continue
        payload = item.get("payload_json")
        if payload is None:
            continue
        payload_bytes += len(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    total = len(body)
    share = (payload_bytes / total) if total else None
    return payload_bytes, share


def fetch_sample(base_url: str, path: str) -> RouteSample:
    url = f"{base_url.rstrip('/')}{path}"
    headers = {"Accept": "application/json", "Cache-Control": "no-cache"}
    request = Request(url, headers=headers, method="GET")
    started = time.perf_counter()
    with urlopen(request, timeout=60) as response:
        body = response.read()
        hdrs = response.headers
        status_code = response.status
    client_ms = (time.perf_counter() - started) * 1000.0
    payload_bytes: int | None = None
    payload_share: float | None = None
    if path.startswith("/api/v1/events"):
        payload_bytes, payload_share = analyze_events_payload(body)
    return RouteSample(
        status_code=status_code,
        client_total_ms=client_ms,
        header_total_ms=_optional_float(hdrs, "X-Perf-Total-Ms"),
        header_db_ms=_optional_float(hdrs, "X-Perf-Db-Ms"),
        header_query_count=_optional_int(hdrs, "X-Perf-Query-Count"),
        response_bytes=len(body),
        correlation_id=hdrs.get("X-Correlation-Id"),
        payload_json_bytes=payload_bytes,
        payload_json_share=payload_share,
    )


def summarize_route(name: str, path: str, samples: list[RouteSample]) -> RouteSummary:
    if not samples:
        return RouteSummary(
            name=name,
            path=path,
            status="NOT_MEASURED",
            warm_client_p95_ms=None,
            warm_header_total_p95_ms=None,
            warm_header_db_p95_ms=None,
            warm_query_count_p95=None,
            warm_response_bytes_p50=None,
            warm_response_bytes_max=None,
            note="no samples",
        )

    client = [s.client_total_ms for s in samples]
    header_total = [s.header_total_ms for s in samples if s.header_total_ms is not None]
    header_db = [s.header_db_ms for s in samples if s.header_db_ms is not None]
    query_counts = [
        float(s.header_query_count) for s in samples if s.header_query_count is not None
    ]
    sizes = [s.response_bytes for s in samples]
    payload_sizes = [s.payload_json_bytes for s in samples if s.payload_json_bytes is not None]
    payload_shares = [s.payload_json_share for s in samples if s.payload_json_share is not None]

    complete = [s for s in samples if sample_has_required_perf_headers(s)]
    if len(complete) == len(samples):
        status = "MEASURED"
        note = ""
    else:
        status = "PARTIAL"
        note = (
            "One or more samples missing required X-Perf-Total-Ms / "
            "X-Perf-Db-Ms / X-Perf-Query-Count; client timings only."
        )

    return RouteSummary(
        name=name,
        path=path,
        status=status,
        warm_client_p95_ms=_percentile(client, 95),
        warm_header_total_p95_ms=_percentile(header_total, 95) if header_total else None,
        warm_header_db_p95_ms=_percentile(header_db, 95) if header_db else None,
        warm_query_count_p95=_percentile(query_counts, 95) if query_counts else None,
        warm_response_bytes_p50=int(statistics.median(sizes)),
        warm_response_bytes_max=max(sizes),
        events_payload_json_bytes_p50=(
            int(statistics.median(payload_sizes)) if payload_sizes else None
        ),
        events_payload_json_share_p50=(
            float(statistics.median(payload_shares)) if payload_shares else None
        ),
        note=note,
    )


def measure(
    base_url: str,
    *,
    warm_runs: int,
    warmup_runs: int,
) -> dict[str, Any]:
    routes: list[dict[str, Any]] = []
    for name, path in AUDIT_ROUTES:
        try:
            # Discarded warm-up probes (direct FastAPI has no browser HTTP cache).
            for _ in range(warmup_runs):
                fetch_sample(base_url, path)
            warm_samples = [fetch_sample(base_url, path) for _ in range(warm_runs)]
            summary = summarize_route(name, path, warm_samples)
        except (HTTPError, URLError, TimeoutError, OSError) as exc:
            summary = RouteSummary(
                name=name,
                path=path,
                status="NOT_MEASURED",
                warm_client_p95_ms=None,
                warm_header_total_p95_ms=None,
                warm_header_db_p95_ms=None,
                warm_query_count_p95=None,
                warm_response_bytes_p50=None,
                warm_response_bytes_max=None,
                note=f"{type(exc).__name__}: {exc}",
            )
        routes.append(asdict(summary))
    return {
        "measurement": "layer_c_fastapi",
        "issue": 101,
        "measured_at": datetime.now(UTC).isoformat(),
        "base_url_host_only": base_url.split("://", 1)[-1].split("/", 1)[0],
        "warm_runs": warm_runs,
        "warmup_runs": warmup_runs,
        "warmup_note": (
            "warmup_runs are discarded probes to stabilize the process; "
            "they are not reported as cold-cache measurements."
        ),
        "routes": routes,
        "railway_private_dns_note": (
            "*.railway.internal is only reachable inside the same Railway "
            "project/environment. Measure private Next.js→FastAPI via probe/ssh."
        ),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--base-url",
        default=os.environ.get("PAPER_API_BASE_URL", "http://127.0.0.1:8080"),
    )
    parser.add_argument("--warm-runs", type=int, default=DEFAULT_WARM_RUNS)
    parser.add_argument(
        "--warmup-runs",
        type=int,
        default=DEFAULT_WARMUP_RUNS,
        help="Discarded warm-up probes before measured warm runs (not cold cache).",
    )
    # Backward-compatible alias for earlier --cold-runs flag.
    parser.add_argument("--cold-runs", type=int, default=None, help=argparse.SUPPRESS)
    parser.add_argument(
        "--output",
        default="docs/operations/dashboard-layer-c-api.json",
    )
    args = parser.parse_args(argv)
    warmup = args.warmup_runs if args.cold_runs is None else args.cold_runs
    report = measure(args.base_url, warm_runs=args.warm_runs, warmup_runs=warmup)
    output_path = args.output
    with open(output_path, "w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2)
        handle.write("\n")
    measured = sum(1 for r in report["routes"] if r["status"] == "MEASURED")
    partial = sum(1 for r in report["routes"] if r["status"] == "PARTIAL")
    print(
        f"Wrote {output_path} "
        f"(MEASURED={measured} PARTIAL={partial} / {len(report['routes'])})"
    )
    return 0 if measured else 1


if __name__ == "__main__":
    sys.exit(main())
