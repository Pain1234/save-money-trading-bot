#!/usr/bin/env sh
set -eu

if [ -z "${PAPER_TRADING_DATABASE_URL:-}" ]; then
  echo "PAPER_TRADING_DATABASE_URL is required" >&2
  exit 1
fi

export PAPER_CONTROL_API_ENABLED="${PAPER_CONTROL_API_ENABLED:-false}"
export PAPER_API_HOST="${PAPER_API_HOST:-0.0.0.0}"
export PAPER_API_PORT="${PAPER_API_PORT:-8080}"

exec python -m paper_trading.api_runner
