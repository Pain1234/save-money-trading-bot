# Backtester ↔ paper parity (R-004 / #48)

## Scope (P4)

Shared lifecycle helpers must stay aligned between `services/backtester/` and paper trading:

- Entry/exit slippage application
- Initial/trailing/gap stop references
- Fee accounting on fills

Regression coverage: `tests/paper_trading/test_backtester_parity.py` (CI job `research-repro`).

## Intentional differences

| Area | Backtester | Paper | Notes |
|------|------------|-------|-------|
| Clock | Synthetic event clock | Wall/ops clock for ops loops | Research runs use backtester clock only |
| Data source | HistoricalDataBundle | Live/WS or DB feeds | Parity tests use identical synthetic candles |
| Networking | None | May connect in ops | Research CI forbids live network |

Document new intentional differences here when introduced; do not silently drift.
