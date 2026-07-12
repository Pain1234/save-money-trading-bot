# Paper Trading Lifecycle Integrity Guarantees

This document summarizes production integrity guarantees enforced on branch
`cursor/paper-trading-final-integrity-remediation-v2`.

## Transaction and Ack Semantics (RMR-001)

- Market event processing mutates scheduler state inside explicit DB transactions.
- Detector acknowledgements (`acknowledge_committed`, terminal-failure acks) run only
  after the outer session commit succeeds.
- Deferred or retryable outcomes release uncommitted `RUNNING` scheduler rows so
  partial work cannot block idempotent retries.

## Immutable Recovery Audit (RMR-002)

- Permanent configuration failures remain on the original scheduler run.
- Recovery attempts are append-only rows linked through `recovery_of_run_id` /
  `resolved_by_run_id`.
- Recovery job names include a monotonic generation suffix and never overwrite
  historical failure records.

## Restart-Persistent Fairness (RMR-003)

- Fairness rotates between independent lifecycle groups, not within a group.
- Persistent tables: `market_event_fairness_cursor`, `market_event_group_state`.
- Deferred groups carry `next_attempt_at` backoff; cursor progress survives bridge
  restarts.

## Open-Batch Ordering (RMR-004)

- Daily open groups key on `event_type + candle_open_time`.
- Within a shared open batch the economic order is fixed: **BTC → ETH → SOL**.
- A transient defer on BTC blocks ETH/SOL in the same batch for that poll while
  other groups continue fairly.

## Canonical Constraint Validation (RMR-005)

- Single source: `services/trading_constraints/validation.py`.
- Shared acceptance rules for tick size, quantity step, minimum quantity alignment,
  minimum notional, and finite-value checks.
- Adapters:
  - Production context → `PermanentConfigurationFailure`
  - Risk engine → `RiskError` (`RC_REJECT_DATA`)
  - Paper execution → `MissingSymbolConstraintsError`
- Regression coverage: `tests/trading_constraints/test_constraint_matrix.py`.

## Soak Evidence Identity (RMR-006)

- Live soak evidence is scoped by persisted `soak_run_id`, not mixed DB/app clocks.
- `create_soak_run()` inserts into `soak_runs` using PostgreSQL `clock_timestamp()`.
- Scheduler runs created while a soak is active inherit the active soak ID through
  `PaperTradingRepository.set_active_soak_run_id`.
- Post-soak FAILED `me:*` queries filter on `soak_run_id`, eliminating clock-skew
  false negatives/positives.

## Overflow and Starvation Controls (RMR-007)

- Batch overflow is logged and remaining candidates stay eligible on subsequent polls.
- Persistent fairness prevents starvation between independent lifecycle groups.
- Terminal `COMPLETED` events are not re-executed; permanent failures clear active
  fairness state.

## Verification Commands

```bash
python -m alembic upgrade head
python -m pytest tests -k "constraint_matrix or soak_window or soak_run_id or clock_skew" -vv -s
python -m pytest tests/paper_trading/integration/test_production_lifecycle_full.py -m postgres -vv -s
python -m pytest tests/paper_trading -m postgres -vv --durations=25
python scripts/verify_paper_state.py --database-url-env PAPER_TRADING_DATABASE_URL
python -m mypy services/strategy_engine services/risk_engine services/backtester services/market_data services/paper_trading services/trading_constraints
python -m ruff check services tests migrations scripts
```

Live public soak (testnet only, explicit opt-in):

```powershell
$env:HYPERLIQUID_NETWORK = "testnet"
$env:RUN_PAPER_LIVE_SOAK = "1"
$env:PAPER_LIVE_SOAK_SECONDS = "300"
python -X faulthandler -m pytest tests/paper_trading/soak/test_live_public_data_soak.py -m live -vv -s
```
