#!/usr/bin/env python3
"""Generate a bcrypt password hash for dashboard AUTH_PASSWORD_HASH."""

from __future__ import annotations

import argparse
import getpass
import sys

try:
    import bcrypt
except ImportError:
    print("Install bcrypt: pip install bcrypt", file=sys.stderr)
    raise SystemExit(1) from None


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate bcrypt hash for dashboard AUTH_PASSWORD_HASH Railway variable."
    )
    parser.add_argument(
        "--password",
        help="Password to hash (omit to prompt securely)",
    )
    args = parser.parse_args()
    password = args.password or getpass.getpass("Dashboard password: ")
    if not password:
        raise SystemExit("Password must not be empty")
    hashed = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(rounds=12))
    print(hashed.decode("utf-8"))


if __name__ == "__main__":
    main()
