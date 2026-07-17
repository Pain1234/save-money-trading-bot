#!/usr/bin/env python3
"""Apply mock Codex review JSON with optional reviewed_* overlay (array-safe)."""

from __future__ import annotations

import json
import sys
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) != 7:
        print(
            "usage: apply_mock_result.py <mock> <out> <base> <head> <diff_hash> "
            "<preserve 0|1> <overlay_env>",
            file=sys.stderr,
        )
        return 2
    mock_path, out_path, base, head, diff_hash, preserve, overlay_env = args
    if overlay_env == "__DEFAULT__":
        overlay_env = ""
    data = json.loads(Path(mock_path).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        print("Mock result root must be a JSON object.", file=sys.stderr)
        return 1
    preserve_b = preserve == "1"
    placeholders = {"WILL_BE_SET", "PLACEHOLDER", "TBD"}

    def is_ph(v: object) -> bool:
        s = str(v)
        return s in placeholders or s.startswith("WILL_BE_SET")

    has_ph = any(
        is_ph(data.get(k, ""))
        for k in ("reviewed_base", "reviewed_head", "reviewed_diff_hash")
    )
    default_overlay = overlay_env != "0"
    if not preserve_b and (default_overlay or has_ph or overlay_env == "1"):
        data["reviewed_base"] = base
        data["reviewed_head"] = head
        data["reviewed_diff_hash"] = diff_hash
    Path(out_path).write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
