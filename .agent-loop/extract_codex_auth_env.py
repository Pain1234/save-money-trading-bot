#!/usr/bin/env python3
"""Extract Codex auth into KEY=value lines for a child process env.

Reads auth.json (ChatGPT login tokens or API key fields) and writes env
assignments to --out-file (preferred) or stdout. Never logs token values.

Auth contract (this project / review gate):
  - ChatGPT tokens.access_token → CODEX_ACCESS_TOKEN only
  - API key (auth.json or env) → CODEX_API_KEY only
  - Never emit OPENAI_API_KEY (gate child env uses CODEX_* only)

Preference order:
  1. Existing process env CODEX_ACCESS_TOKEN / CODEX_API_KEY (when prefer_existing_env)
  2. Existing OPENAI_API_KEY in process env → mapped to CODEX_API_KEY (never kept as OPENAI_*)
  3. auth.json top-level OPENAI_API_KEY / CODEX_API_KEY → CODEX_API_KEY
  4. auth.json tokens.access_token → CODEX_ACCESS_TOKEN

Exit codes:
  0 - at least one usable key written
  1 - auth source missing / unreadable / no usable credential
  2 - usage error
"""

from __future__ import annotations

import argparse
import json
import os
import stat
import sys
from pathlib import Path


def _usable(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        return None
    text = value.strip()
    return text or None


def extract_env_assignments(
    auth_path: Path | None,
    *,
    prefer_existing_env: bool = True,
) -> dict[str, str]:
    """Return env KEY -> value for Codex noninteractive auth (CODEX_* only)."""
    out: dict[str, str] = {}

    if prefer_existing_env:
        access = _usable(os.environ.get("CODEX_ACCESS_TOKEN"))
        if access:
            out["CODEX_ACCESS_TOKEN"] = access
        api = _usable(os.environ.get("CODEX_API_KEY"))
        if api:
            out["CODEX_API_KEY"] = api
        # Legacy parent env: map OPENAI_API_KEY → CODEX_API_KEY (never emit OPENAI_*).
        if "CODEX_API_KEY" not in out:
            legacy = _usable(os.environ.get("OPENAI_API_KEY"))
            if legacy:
                out["CODEX_API_KEY"] = legacy

    if "CODEX_ACCESS_TOKEN" in out or "CODEX_API_KEY" in out:
        return out

    if auth_path is None:
        return out

    raw = auth_path.read_text(encoding="utf-8")
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError("auth.json root must be an object")

    for key in ("CODEX_API_KEY", "OPENAI_API_KEY"):
        val = _usable(data.get(key))
        if val:
            out["CODEX_API_KEY"] = val
            break

    if "CODEX_API_KEY" not in out:
        tokens = data.get("tokens")
        if isinstance(tokens, dict):
            access = _usable(tokens.get("access_token"))
            if access:
                out["CODEX_ACCESS_TOKEN"] = access

    return out


def _write_env_file(path: Path, assignments: dict[str, str]) -> None:
    lines = [f"{k}={v}" for k, v in assignments.items()]
    text = "\n".join(lines) + ("\n" if lines else "")
    path.write_text(text, encoding="utf-8")
    try:
        path.chmod(stat.S_IRUSR | stat.S_IWUSR)  # 0o600
    except OSError:
        # Windows may ignore Unix mode bits; still avoid world-writable if possible.
        pass


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Extract Codex auth into KEY=value env assignments (CODEX_* only)."
    )
    parser.add_argument(
        "--auth-json",
        type=Path,
        default=None,
        help="Path to Codex auth.json (optional if env already has CODEX_* keys).",
    )
    parser.add_argument(
        "--out-file",
        type=Path,
        default=None,
        help="Write KEY=value lines here (mode 600). Prefer over stdout.",
    )
    parser.add_argument(
        "--ignore-existing-env",
        action="store_true",
        help="Do not reuse CODEX_ACCESS_TOKEN/CODEX_API_KEY already in the process env.",
    )
    args = parser.parse_args(argv)

    auth_path = args.auth_json
    if auth_path is not None and not auth_path.is_file():
        print(
            f"extract_codex_auth_env: auth.json not found: {auth_path}",
            file=sys.stderr,
        )
        return 1

    try:
        assignments = extract_env_assignments(
            auth_path,
            prefer_existing_env=not args.ignore_existing_env,
        )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"extract_codex_auth_env: error: {exc}", file=sys.stderr)
        return 1

    if not assignments:
        print(
            "extract_codex_auth_env: no usable CODEX_ACCESS_TOKEN/CODEX_API_KEY found",
            file=sys.stderr,
        )
        return 1

    # Defense: never write OPENAI_API_KEY.
    assignments = {k: v for k, v in assignments.items() if k != "OPENAI_API_KEY"}

    if args.out_file is not None:
        try:
            _write_env_file(args.out_file, assignments)
        except OSError as exc:
            print(f"extract_codex_auth_env: cannot write out-file: {exc}", file=sys.stderr)
            return 1
        # Do not print secrets; only confirm keys present.
        print(
            "extract_codex_auth_env: wrote keys: " + ",".join(sorted(assignments)),
            file=sys.stderr,
        )
        return 0

    # stdout fallback (tests / piping). Callers must not log this stream.
    for key, value in assignments.items():
        sys.stdout.write(f"{key}={value}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
