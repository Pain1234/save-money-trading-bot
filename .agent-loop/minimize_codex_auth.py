#!/usr/bin/env python3
"""Write a minimized Codex auth.json for ephemeral CODEX_HOME.

Never copies the full user auth file. Only ChatGPT token fields required by
Codex CLI 0.144+ (id_token + access_token + refresh/account when present).
Strips OPENAI_API_KEY and any unrelated top-level secrets.

Exit codes:
  0 - minimized auth written
  1 - source missing / unusable
  2 - usage error
"""

from __future__ import annotations

import argparse
import json
import os
import stat
import sys
from pathlib import Path

_TOKEN_KEYS = ("access_token", "id_token", "refresh_token", "account_id")


def minimize_auth(data: dict) -> dict:
    """Return a minimized auth object safe to place in ephemeral CODEX_HOME."""
    out: dict = {}
    mode = data.get("auth_mode")
    if isinstance(mode, str) and mode.strip():
        out["auth_mode"] = mode.strip()

    tokens_in = data.get("tokens")
    tokens_out: dict[str, str] = {}
    if isinstance(tokens_in, dict):
        for key in _TOKEN_KEYS:
            val = tokens_in.get(key)
            if isinstance(val, str) and val.strip():
                tokens_out[key] = val.strip()
    if tokens_out:
        out["tokens"] = tokens_out

    # Never copy OPENAI_API_KEY / CODEX_API_KEY into the file — use env for API keys.
    return out


def usable(minimized: dict) -> bool:
    tokens = minimized.get("tokens")
    if not isinstance(tokens, dict):
        return False
    # ChatGPT login needs both id_token and access_token on Codex 0.144+.
    return bool(tokens.get("access_token") and tokens.get("id_token"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--auth-json", type=Path, required=True)
    parser.add_argument("--out-file", type=Path, required=True)
    args = parser.parse_args(argv)

    src = args.auth_json
    if not src.is_file():
        print(f"minimize_codex_auth: missing source {src}", file=sys.stderr)
        return 1

    try:
        data = json.loads(src.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        print(f"minimize_codex_auth: cannot read source: {exc}", file=sys.stderr)
        return 1

    if not isinstance(data, dict):
        print("minimize_codex_auth: auth.json root must be an object", file=sys.stderr)
        return 1

    minimized = minimize_auth(data)
    if not usable(minimized):
        print(
            "minimize_codex_auth: source lacks usable ChatGPT tokens "
            "(need tokens.access_token and tokens.id_token)",
            file=sys.stderr,
        )
        return 1

    out = args.out_file
    out.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(minimized, indent=2) + "\n"
    # Write privately then tighten perms (best-effort on Windows).
    out.write_text(payload, encoding="utf-8")
    try:
        os.chmod(out, stat.S_IRUSR | stat.S_IWUSR)
    except OSError:
        pass

    # Never print token values — only field names.
    token_keys = sorted((minimized.get("tokens") or {}).keys())
    print(
        f"minimize_codex_auth: wrote fields auth_mode={bool(minimized.get('auth_mode'))} "
        f"token_keys={token_keys}",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
