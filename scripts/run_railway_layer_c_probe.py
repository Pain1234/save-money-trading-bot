"""Upload Layer C probe via SSH and capture UTF-8 JSON artifact."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PROBE = REPO / "scripts" / "railway_layer_c_probe.js"
OUT = REPO / "docs" / "operations" / "dashboard-layer-c-api-railway.json"
HOST = "railway-paper-trading-dashboard"


def main() -> int:
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
            "node /tmp/railway_layer_c_probe.js",
        ],
        capture_output=True,
        check=False,
    )
    if run.returncode != 0:
        sys.stderr.write(run.stderr.decode("utf-8", errors="replace"))
        print(f"probe failed: {run.returncode}", file=sys.stderr)
        if run.stdout:
            OUT.write_bytes(run.stdout)
        return run.returncode or 1

    OUT.write_bytes(run.stdout)
    print(f"wrote {OUT} ({OUT.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
