#!/usr/bin/env sh
set -eu

if [ -z "${PAPER_TRADING_DATABASE_URL:-}" ]; then
  echo "PAPER_TRADING_DATABASE_URL is required" >&2
  exit 1
fi

python -m alembic upgrade head
python scripts/verify_paper_state.py --database-url-env PAPER_TRADING_DATABASE_URL

export PAPER_API_ENABLED="${PAPER_API_ENABLED:-false}"
export PAPER_PRODUCTION_MODE="${PAPER_PRODUCTION_MODE:-true}"
export PAPER_CONTROL_API_ENABLED="${PAPER_CONTROL_API_ENABLED:-false}"
export PAPER_SCHEDULER_ENABLED="${PAPER_SCHEDULER_ENABLED:-true}"
export HYPERLIQUID_NETWORK="${HYPERLIQUID_NETWORK:-testnet}"
export PAPER_FUNDING_ENABLED="${PAPER_FUNDING_ENABLED:-false}"

exec python -m paper_trading
