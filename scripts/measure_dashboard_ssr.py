#!/usr/bin/env python3
"""Layer B — Next.js SSR / TTFB measurement for Issue #101.

Measures authenticated dashboard HTML responses from the *public* dashboard URL
(browser → Next.js). This does **not** hit ``*.railway.internal``.

Usage:
    export PAPER_DASHBOARD_BASE_URL=https://bot.save-money.xyz
    export PAPER_DASHBOARD_USER=...
    export PAPER_DASHBOARD_PASSWORD=...
    python scripts/measure_dashboard_ssr.py --warm-runs 10 \\
        --output docs/operations/dashboard-layer-b-ssr.json
"""

from __future__ import annotations

import argparse
import http.cookiejar
import json
import os
import sys
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from urllib.error import HTTPError, URLError

DASHBOARD_ROUTES: tuple[tuple[str, str], ...] = (
    ("overview", "/dashboard"),
    ("status", "/dashboard/status"),
    ("positions", "/dashboard/positions"),
    ("orders", "/dashboard/orders"),
    ("fills", "/dashboard/fills"),
    ("equity", "/dashboard/equity"),
    ("incidents", "/dashboard/incidents"),
)

DASHBOARD_AUTH_MARKER = "Paper Trading Monitor"


@dataclass(frozen=True)
class SsrSample:
    status_code: int
    ttfb_ms: float
    total_ms: float
    html_bytes: int
    cache_header: str | None
    final_url: str
    authenticated: bool


def _percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, int(round((pct / 100.0) * (len(ordered) - 1)))))
    return ordered[index]


def is_authenticated_dashboard(
    requested_path: str,
    final_url: str,
    body: bytes,
    *,
    marker: str = DASHBOARD_AUTH_MARKER,
) -> bool:
    """Reject login redirects and unauthenticated HTML masquerading as SSR hits."""
    path = urllib.parse.urlparse(final_url).path.rstrip("/") or "/"
    requested = requested_path.rstrip("/") or "/"
    if path == "/login" or path.endswith("/login"):
        return False
    if path != requested:
        return False
    text = body.decode("utf-8", errors="replace")
    return marker in text


def _login(opener: urllib.request.OpenerDirector, base_url: str, user: str, password: str) -> None:
    login_url = f"{base_url.rstrip('/')}/api/auth/login"
    body = json.dumps({"username": user, "password": password}).encode("utf-8")
    request = urllib.request.Request(
        login_url,
        data=body,
        method="POST",
        headers={"Content-Type": "application/json", "Accept": "application/json"},
    )
    with opener.open(request, timeout=60) as response:
        if response.status >= 400:
            raise RuntimeError(f"login failed HTTP {response.status}")


def fetch_html(
    opener: urllib.request.OpenerDirector,
    base_url: str,
    path: str,
    *,
    cold: bool,
) -> SsrSample:
    url = f"{base_url.rstrip('/')}{path}"
    headers = {"Accept": "text/html"}
    if cold:
        headers["Cache-Control"] = "no-cache"
        headers["Pragma"] = "no-cache"
    request = urllib.request.Request(url, headers=headers, method="GET")
    started = time.perf_counter()
    with opener.open(request, timeout=60) as response:
        # First byte availability approximated by headers-ready before full read.
        ttfb_ms = (time.perf_counter() - started) * 1000.0
        body = response.read()
        total_ms = (time.perf_counter() - started) * 1000.0
        status_code = response.status
        cache_header = response.headers.get("Cache-Control")
        final_url = response.geturl()
    authenticated = is_authenticated_dashboard(path, final_url, body)
    return SsrSample(
        status_code=status_code,
        ttfb_ms=ttfb_ms,
        total_ms=total_ms,
        html_bytes=len(body),
        cache_header=cache_header,
        final_url=final_url,
        authenticated=authenticated,
    )


def measure(
    base_url: str,
    user: str,
    password: str,
    *,
    warm_runs: int,
    cold_runs: int,
) -> dict[str, Any]:
    jar = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
    try:
        _login(opener, base_url, user, password)
    except (HTTPError, URLError, TimeoutError, OSError, RuntimeError) as exc:
        return {
            "measurement": "layer_b_nextjs_ssr",
            "issue": 101,
            "status": "NOT_MEASURED",
            "measured_at": datetime.now(UTC).isoformat(),
            "note": f"login failed: {type(exc).__name__}: {exc}",
            "routes": [],
        }

    routes: list[dict[str, Any]] = []
    for name, path in DASHBOARD_ROUTES:
        try:
            for _ in range(cold_runs):
                probe = fetch_html(opener, base_url, path, cold=True)
                if not probe.authenticated:
                    raise RuntimeError(
                        f"unauthenticated response during warmup: {probe.final_url}"
                    )
            samples = [fetch_html(opener, base_url, path, cold=False) for _ in range(warm_runs)]
            if not samples or any(not s.authenticated for s in samples):
                bad = next((s for s in samples if not s.authenticated), None)
                routes.append(
                    {
                        "name": name,
                        "path": path,
                        "status": "NOT_MEASURED",
                        "warm_ttfb_p95_ms": None,
                        "warm_total_p95_ms": None,
                        "html_bytes_p50": None,
                        "html_bytes_max": None,
                        "final_url": bad.final_url if bad else None,
                        "note": (
                            "Login redirect or missing dashboard auth marker "
                            f"({DASHBOARD_AUTH_MARKER!r}); sample discarded."
                        ),
                    }
                )
                continue
            ttfbs = [s.ttfb_ms for s in samples]
            totals = [s.total_ms for s in samples]
            sizes = [s.html_bytes for s in samples]
            routes.append(
                {
                    "name": name,
                    "path": path,
                    "status": "MEASURED",
                    "warm_ttfb_p95_ms": _percentile(ttfbs, 95),
                    "warm_total_p95_ms": _percentile(totals, 95),
                    "html_bytes_p50": int(sorted(sizes)[len(sizes) // 2]),
                    "html_bytes_max": max(sizes),
                    "final_url": samples[0].final_url,
                    "authenticated": True,
                    "note": (
                        "TTFB approximates headers-ready; full HTML includes "
                        "SSR + server-side FastAPI fetches for this route."
                    ),
                }
            )
        except (HTTPError, URLError, TimeoutError, OSError, RuntimeError) as exc:
            routes.append(
                {
                    "name": name,
                    "path": path,
                    "status": "NOT_MEASURED",
                    "warm_ttfb_p95_ms": None,
                    "warm_total_p95_ms": None,
                    "html_bytes_p50": None,
                    "html_bytes_max": None,
                    "note": f"{type(exc).__name__}: {exc}",
                }
            )
    return {
        "measurement": "layer_b_nextjs_ssr",
        "issue": 101,
        "status": "MEASURED" if any(r["status"] == "MEASURED" for r in routes) else "NOT_MEASURED",
        "measured_at": datetime.now(UTC).isoformat(),
        "base_url_host_only": base_url.split("://", 1)[-1].split("/", 1)[0],
        "warm_runs": warm_runs,
        "cold_runs": cold_runs,
        "auth_marker": DASHBOARD_AUTH_MARKER,
        "routes": routes,
        "layers": [
            "Browser → Next.js (this script)",
            "Next.js SSR + server fetches to FastAPI (included in TTFB/total)",
            "FastAPI → PostgreSQL (see Layer C / D)",
            "Browser rendering (see Layer A Playwright)",
        ],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--base-url",
        default=os.environ.get("PAPER_DASHBOARD_BASE_URL", "http://127.0.0.1:3000"),
    )
    parser.add_argument("--user", default=os.environ.get("PAPER_DASHBOARD_USER", ""))
    parser.add_argument("--password", default=os.environ.get("PAPER_DASHBOARD_PASSWORD", ""))
    parser.add_argument("--warm-runs", type=int, default=10)
    parser.add_argument("--cold-runs", type=int, default=2)
    parser.add_argument(
        "--output",
        default="docs/operations/dashboard-layer-b-ssr.json",
    )
    args = parser.parse_args(argv)
    if not args.user or not args.password:
        report = {
            "measurement": "layer_b_nextjs_ssr",
            "issue": 101,
            "status": "NOT_MEASURED",
            "measured_at": datetime.now(UTC).isoformat(),
            "note": "Set PAPER_DASHBOARD_USER and PAPER_DASHBOARD_PASSWORD",
            "routes": [],
        }
        with open(args.output, "w", encoding="utf-8") as handle:
            json.dump(report, handle, indent=2)
            handle.write("\n")
        print(f"Wrote {args.output} (NOT_MEASURED — credentials missing)")
        return 1
    report = measure(
        args.base_url,
        args.user,
        args.password,
        warm_runs=args.warm_runs,
        cold_runs=args.cold_runs,
    )
    with open(args.output, "w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2)
        handle.write("\n")
    print(f"Wrote {args.output} (status={report.get('status')})")
    return 0 if report.get("status") == "MEASURED" else 1


if __name__ == "__main__":
    sys.exit(main())
