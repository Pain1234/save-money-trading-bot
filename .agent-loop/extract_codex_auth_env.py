#!/usr/bin/env python3
"""Extract Codex/OpenAI auth into KEY=value lines for a child process env.

Reads auth.json (ChatGPT login tokens or API key fields) and writes env
assignments to --out-file (preferred) or stdout. Never logs token values.

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
    """Return env KEY -> value for Codex noninteractive auth.

    Preference order for OPENAI_API_KEY:
      1. Existing process env OPENAI_API_KEY / CODEX_API_KEY (when prefer_existing_env)
      2. auth.json top-level OPENAI_API_KEY / CODEX_API_KEY
      3. auth.json tokens.access_token (ChatGPT login)
    """
    out: dict[str, str] = {}

    if prefer_existing_env:
        for key in ("OPENAI_API_KEY", "CODEX_API_KEY"):
            existing = _usable(os.environ.get(key))
            if existing:
                out[key] = existing

    if "OPENAI_API_KEY" in out or "CODEX_API_KEY" in out:
        return out

    if auth_path is None:
        return out

    raw = auth_path.read_text(encoding="utf-8")
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError("auth.json root must be an object")

    for key in ("OPENAI_API_KEY", "CODEX_API_KEY"):
        val = _usable(data.get(key))
        if val:
            out[key] = val

    if "OPENAI_API_KEY" not in out and "CODEX_API_KEY" not in out:
        tokens = data.get("tokens")
        if isinstance(tokens, dict):
            access = _usable(tokens.get("access_token"))
            if access:
                # Codex noninteractive path: ChatGPT access token via OPENAI_API_KEY.
                out["OPENAI_API_KEY"] = access

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
        description="Extract Codex auth into KEY=value env assignments."
    )
    parser.add_argument(
        "--auth-json",
        type=Path,
        default=None,
        help="Path to Codex auth.json (optional if env already has API keys).",
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
        help="Do not reuse OPENAI_API_KEY/CODEX_API_KEY already in the process env.",
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
            "extract_codex_auth_env: no usable OPENAI_API_KEY/CODEX_API_KEY found",
            file=sys.stderr,
        )
        return 1

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
