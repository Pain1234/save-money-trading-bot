"""Upload Layer C probe via SSH and capture UTF-8 JSON artifact.

Usage:
  python scripts/run_railway_layer_c_probe.py \\
    --output docs/operations/dashboard-layer-c-before-121.json \\
    --issue 121 \\
    --routes wallet,dashboard_summary,status
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PROBE = REPO / "scripts" / "railway_layer_c_probe.js"
DEFAULT_OUT = REPO / "docs" / "operations" / "dashboard-layer-c-api-railway.json"
HOST = "railway-paper-trading-dashboard"

DEFAULT_DASHBOARD_REGION = "europe-west4-drams3a"
DEFAULT_POSTGRES_REGION = "europe-west4-drams3a"


def resolve_regions() -> dict[str, str]:
    """Caller-supplied regions override any probe defaults (never invent ``sfo``)."""
    return {
        "paper-trading-dashboard": os.environ.get(
            "LAYER_C_DASHBOARD_REGION", DEFAULT_DASHBOARD_REGION
        ),
        "paper-trading-postgres": os.environ.get(
            "LAYER_C_POSTGRES_REGION", DEFAULT_POSTGRES_REGION
        ),
        "paper-trading-api": os.environ.get("LAYER_C_API_REGION", "NOT_MEASURED"),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--issue", type=int, default=121)
    parser.add_argument(
        "--routes",
        default="",
        help="Comma-separated probe route names (empty = all).",
    )
    parser.add_argument("--warm-runs", type=int, default=20)
    parser.add_argument("--warmup-runs", type=int, default=3)
    parser.add_argument(
        "--phase",
        default="",
        help="Optional label stored in artifact (e.g. before-region, after-region).",
    )
    parser.add_argument(
        "--api-region",
        default="",
        help="Overrides LAYER_C_API_REGION for artifact metadata.",
    )
    args = parser.parse_args(argv)
    if args.api_region:
        os.environ["LAYER_C_API_REGION"] = args.api_region

    probe_text = PROBE.read_text(encoding="utf-8")
    upload = subprocess.run(
        [
            "ssh",
            "-o",
            "BatchMode=yes",
            "-o",
            "ConnectTimeout=30",
            HOST,
            "cat > /tmp/railway_layer_c_probe.js",
        ],
        input=probe_text.encode("utf-8"),
        capture_output=True,
        check=False,
    )
    if upload.returncode != 0:
        sys.stderr.write(upload.stderr.decode("utf-8", errors="replace"))
        print(f"upload failed: {upload.returncode}", file=sys.stderr)
        return upload.returncode or 1

    regions = resolve_regions()
    remote_env = (
        f"LAYER_C_ISSUE={args.issue} "
        f"LAYER_C_WARM_RUNS={args.warm_runs} "
        f"LAYER_C_WARMUP_RUNS={args.warmup_runs} "
        f"LAYER_C_API_REGION={regions['paper-trading-api']} "
        f"LAYER_C_DASHBOARD_REGION={regions['paper-trading-dashboard']} "
        f"LAYER_C_POSTGRES_REGION={regions['paper-trading-postgres']} "
    )
    if args.routes:
        remote_env += f"LAYER_C_ROUTES={args.routes} "

    run = subprocess.run(
        [
            "ssh",
            "-o",
            "BatchMode=yes",
            "-o",
            "ConnectTimeout=30",
            "-o",
            "ServerAliveInterval=30",
            HOST,
            f"{remote_env}node /tmp/railway_layer_c_probe.js",
        ],
        capture_output=True,
        check=False,
    )
    if run.returncode != 0:
        sys.stderr.write(run.stderr.decode("utf-8", errors="replace"))
        print(f"probe failed: {run.returncode}", file=sys.stderr)
        if run.stdout:
            args.output.write_bytes(run.stdout)
        return run.returncode or 1

    report = json.loads(run.stdout.decode("utf-8"))
    report["issue"] = args.issue
    report["phase"] = args.phase or report.get("phase")
    report["captured_at_utc"] = datetime.now(UTC).isoformat()
    report["local_git_head"] = (
        subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO).decode().strip()
    )
    # Always overwrite probe defaults with explicit caller/env metadata.
    report["regions"] = resolve_regions()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {args.output} ({args.output.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
