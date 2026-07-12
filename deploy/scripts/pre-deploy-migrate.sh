#!/usr/bin/env sh
set -eu

if [ -z "${PAPER_TRADING_DATABASE_URL:-}" ]; then
  echo "PAPER_TRADING_DATABASE_URL is required" >&2
  exit 1
fi

python -m alembic upgrade head
