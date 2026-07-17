# Backtester ↔ paper parity (R-004 / #48)

## Scope (P4)

Shared lifecycle helpers and **signal decisions** must stay aligned:

- Entry/exit slippage application (`test_backtester_parity.py`)
- Initial/trailing/gap stop references
- Fee accounting on fills
- Strategy signal kinds / entry types / reason codes on identical candles
  (`test_backtester_signal_parity.py`)

Regression coverage in CI job `research-repro`:
- `tests/paper_trading/test_backtester_parity.py`
- `tests/paper_trading/test_backtester_signal_parity.py`

Postgres replay E2E (`tests/paper_trading/replay/`) remains a stronger integration
check but is **not** required for the offline research gate.

## Intentional differences

| Area | Backtester | Paper | Notes |
|------|------------|-------|-------|
| Clock | Synthetic event clock | Wall/ops clock for ops loops | Research runs use backtester clock only |
| Data source | HistoricalDataBundle | Live/WS or DB feeds | Parity tests use identical synthetic candles |
| Networking | None | May connect in ops | Research CI forbids live network |
| Persistence | In-memory result | DB-backed orchestrator (replay) | Signal parity test avoids DB |

Document new intentional differences here when introduced; do not silently drift.
