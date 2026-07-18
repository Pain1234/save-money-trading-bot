#!/usr/bin/env sh
set -eu

if [ -z "${PAPER_TRADING_DATABASE_URL:-}" ]; then
  echo "PAPER_TRADING_DATABASE_URL is required" >&2
  exit 1
fi

export PAPER_CONTROL_API_ENABLED="${PAPER_CONTROL_API_ENABLED:-false}"
export PAPER_API_HOST="${PAPER_API_HOST:-0.0.0.0}"
export PAPER_API_PORT="${PAPER_API_PORT:-8080}"

# Research Lab (#270): local_lab catalog ships in the image under /app/examples.
export RESEARCH_REPO_ROOT="${RESEARCH_REPO_ROOT:-/app}"
export RESEARCH_ARTIFACTS_ROOT="${RESEARCH_ARTIFACTS_ROOT:-/app}"
if [ -z "${RESEARCH_DATASET_CATALOG_PATH:-}" ] \
  && [ -f /app/examples/research/local_lab/catalog.json ]; then
  export RESEARCH_DATASET_CATALOG_PATH=/app/examples/research/local_lab/catalog.json
fi

# Research Lab (#272): API image has no .git — pin deploy commit from Railway.
if [ -z "${RESEARCH_GIT_COMMIT:-}" ] && [ -n "${RAILWAY_GIT_COMMIT_SHA:-}" ]; then
  export RESEARCH_GIT_COMMIT="$RAILWAY_GIT_COMMIT_SHA"
fi

exec python -m paper_trading.api_runner
