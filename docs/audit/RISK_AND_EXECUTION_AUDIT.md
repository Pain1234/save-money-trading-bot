# Risk and Execution Audit — Auditor B

Independent scope: Risk Engine, Strategy→Risk→Paper contract, order/fill lifecycle,
entry/readiness gates, stops, restart/idempotency, and execution edge cases. Audit
basis is Issue #371 at commit
`7b78eb9996eb16e6d2ec6a00c2e1908c518682d9`. No repair or parameter change was made.

## Summary

The pure Risk Engine is deterministic and fail-closed for the exercised V1 limits,
NaN/Infinity, invalid/missing constraints, duplicate symbols/intents, rounding,
leverage, margin and exact portfolio boundary. All 50 Risk Engine tests passed.
The end-to-end execution contract is not safe to call fully verified: production pause
gating is wired to the wrong field, already-scheduled entries are not re-gated at fill
time, recovery omits economic reconciliation, and several modeled lifecycle states are
only scaffolding.

Overall Auditor-B decision for this slice: **`CONTINUE_WITH_RESTRICTIONS`**. Do not
start P6 soak or claim unsupervised paper readiness until B-FINDING-01 through
B-FINDING-03 are resolved and PostgreSQL regression evidence is green. No evidence in
this audit justifies live/P8 work.

## Risk rule table

Percent values in code are fractions (`0.005` = 0.5%, `0.02` = 2%). Frozen defaults
are documented in `docs/strategy-v1-parameter-inventory.md:59-69`.

| Rule / edge | Soll | Code evidence | Test evidence | Result |
|---|---|---|---|---|
| Equity finite and > 0; margin finite and >= 0 | Risk spec `docs/risk-specification.md:292-298` | `risk_engine/validation.py:38-59` | zero/negative/NaN/Infinity in `tests/risk_engine/test_risk_evaluate.py:56-81` and `test_risk_determinism.py:35-52` | `VERIFIED` |
| Parameters cannot exceed frozen maxima | Freeze inventory | `risk_engine/validation.py:68-96` | max leverage 2.0001 rejected (`test_risk_evaluate.py:263-271`) | `VERIFIED` |
| Constraints positive, finite; missing fails closed | Exchange constraints contract | shared validator via `risk_engine/validation.py:60-65`; paper requires explicit constraints at `paper_trading/execution.py:109-117` | invalid step and missing constraints passed | `VERIFIED` |
| Proposal long-only, signal approved, data OK, runtime ACTIVE | Strategy→Risk contract | `risk_engine/validation.py:129-186` | wrong side/signal, incomplete data, missing approval passed | `VERIFIED` |
| Stop below entry and positive distance | Risk spec §3 | rounded down then validated (`risk_engine/engine.py:139-153`) | stop above entry/negative stop passed | `VERIFIED` |
| 0.5% trade-risk sizing; quantity floors | Frozen limit | `risk_engine/sizing.py:54-109`; post-round cap at `:23-51` | sizing and zero-after-round tests passed | `VERIFIED` |
| Leverage only reduces size; max 2.0 | Risk spec §6 | `risk_engine/sizing.py:111-131`; final check `risk_engine/engine.py:357-371` | risk suite passed | `VERIFIED` |
| Available margin only reduces size | Paper/risk contract | `risk_engine/sizing.py:133-153`; final check `risk_engine/engine.py:373-387` | risk suite passed | `VERIFIED` |
| Max three open positions / one per symbol | Risk spec §5 | duplicate first, count second (`risk_engine/engine.py:170-222`) | exact collision and three-position rejection passed | `VERIFIED` |
| Current risk uses max(initial, trail), clamp at zero | Risk spec §4.2 | `risk_engine/portfolio.py:10-25` | portfolio tests passed | `VERIFIED` |
| Projected actual portfolio risk <= 2% | Risk spec §4.3 | actual rounded risk and strict `>` reject (`risk_engine/engine.py:333-355`) | exactly 2% accepted (`test_risk_evaluate.py:133-143`); slight over rejected (`:441-456`) | `VERIFIED` |
| Duplicate deterministic intent rejected | Idempotent command contract | `risk_engine/engine.py:157-169`; DB unique key `paper_trading/db/orm.py:85-120` | duplicate tests passed | `VERIFIED` |
| NaN/Infinity in open position/ATR/account rejected | Fail-closed | `risk_engine/validation.py:38-186` | account, mark and daily-loss NaN tests passed | `VERIFIED` |
| Missing/extreme min quantity/notional | Fail-closed | `risk_engine/engine.py:295-331` | min quantity/notional extremes passed | `VERIFIED` |
| Pause/kill block all new entry risk | README and orchestrator contract | Contradictions described below | Existing E2E covers intent creation only and does not use production builder | `CONTRADICTED` |

## Strategy→Risk→Paper contract

### Soll

Strategy produces a `LONG_ENTRY` intent; risk alone authorizes quantity; paper execution
simulates the fill and persists the economic chain. Signal strength cannot increase
size or bypass portfolio/leverage limits.

### Code

1. Strategy evaluation is persisted idempotently before an intent
   (`services/paper_trading/evaluation.py:53-169`).
2. Entry gates validate allowed symbol, readiness, existing symbol/intent, position
   count, signal, stop and ATR (`services/paper_trading/lifecycle.py:131-166`).
3. At next open, slippage-adjusted price and a fill-based initial stop are calculated
   before Risk Engine evaluation (`services/paper_trading/execution.py:126-174`).
4. Only `RiskDecision.rounded_quantity` reaches accounting and persistence
   (`services/paper_trading/execution.py:159-184`).
5. Successful entry writes one market-at-open order, one ENTRY fill, fee/slippage,
   position and terminal intent in one transaction (`execution.py:345-449`).

This positive path is `VERIFIED` in code and unit tests. Runtime deployment remains
`NOT_VERIFIABLE`.

### Contract breaks

- `ProductionContextBuilder._runtime_gates()` calculates `paused` as
  `runtime.status == RuntimeStatus.PAUSED` (`scheduler_context.py:91-98`), while the
  control API changes only `runtime.paused` (`runtime.py:95-109`, `api.py:525-535`).
  Safe in-memory reproduction returned `(True, False, False)` for
  `{status=READY, paused=True, kill_switch=False}`. This is B-FINDING-01.
- A scheduled fill is not passed entry readiness, pause, or kill state. The fill context
  has no such fields (`lifecycle.py:103-115`), processing does not reread runtime
  (`lifecycle.py:242-319`), and the shared adapter supplies `BotSystemState.ACTIVE` by
  default (`backtester/paper_lifecycle.py:108-150`). This is B-FINDING-02.

## Order lifecycle, restart, cancel, and partial fills

| Capability | Evidence | Status |
|---|---|---|
| Evaluation/intent idempotency | unique evaluation and intent constraints (`db/orm.py:73-120`) | `VERIFIED` |
| One entry order per intent | unique `paper_orders.intent_id` (`db/orm.py:124-149`) | `VERIFIED` |
| Fill idempotency | deterministic key + `(order,candle,sequence)` uniqueness (`db/orm.py:152-191`); early existing-fill return (`execution.py:258-260`, `:317-343`) | `VERIFIED` statically; DB run unavailable |
| Restart orphan cleanup | RUNNING runs auto-failed (`recovery.py:95-105`) | `PARTIALLY_VERIFIED`; PostgreSQL tests unavailable |
| Duplicate fill recovery | duplicate deterministic keys fatal (`recovery.py:540-553`) | `PARTIALLY_VERIFIED`; database uniqueness normally prevents construction |
| Partial fill | Enum/schema allow `PARTIALLY_FILLED` and `remaining_quantity`, but production writes one fill and zero remaining (`execution.py:358-390`) | `NOT_IMPLEMENTED` |
| Cancel | Enum/transitions exist; no cancel service/API or production call found | `NOT_IMPLEMENTED` |
| Persistent initial stop order | `STOP_MARKET` enum exists, but entry creates only `MARKET_AT_OPEN`; protection is position fields + scheduler | `NOT_IMPLEMENTED` relative to risk spec |
| Trailing cancel-replace | Stop history + position stop update, no order cancel/replace (`stops.py:67-165`) | `DOCUMENTATION_DRIFT` / simulated equivalent only |

The test named `test_partial_fill_flow_commits_atomically` asserts exactly one full fill
and one open position (`tests/paper_trading/failure/test_crash_boundaries.py:44-53`); it
does not exercise partial-fill sizing, remaining quantity, multiple fill sequence, or
stop resizing. See B-FINDING-07.

## Stop and exit safety

Positive evidence:

- Daily open checks pre-existing gap stops before new fills
  (`services/paper_trading/scheduler.py:190-225`).
- Gap detection uses only the known open, not future low
  (`services/backtester/paper_lifecycle.py:193-201`;
  `tests/paper_trading/test_stop_gap_intraday_contract.py:18-28`).
- Intraday checks use the live partial low (`paper_lifecycle.py:204-224`).
- Trailing stop updates require a closed candle and only persist increases
  (`services/paper_trading/stops.py:67-165`), reinforced by database constraints
  (`db/orm.py:225-259`).
- Exit fill, wallet and position close are one transaction (`stops.py:269-326`).

Contradiction: the frozen spec states gap exit at the open exactly
(`docs/risk-specification.md:260-273`), but every stop—including gap—passes the open
reference through adverse exit slippage (`stops.py:261-267`;
`backtester/paper_lifecycle.py:246-260`). Existing gap tests assert only the trigger
reference, not persisted fill price (`test_stop_gap_intraday_contract.py:18-23`). See
B-FINDING-05.

## Candidate findings

### B-FINDING-01 — Production pause flag does not block intent creation

- Severity: **S2 High**
- Impact: local/dev control pause can be accepted and reported while the production
  context still permits a new intent. This violates the documented operator control;
  no real capital is exposed because live execution is absent.
- Confidence: **High**, static trace plus safe in-memory reproduction.
- Soll: pause blocks new intents/entries (`services/paper_trading/README.md:88-91`).
- Ist: API sets `runtime.paused`; production builder ignores that field and compares
  status enum instead (`api.py:525-535`; `scheduler_context.py:91-98`).
- Reproduction: with audit worktree on `PYTHONPATH`, construct a READY runtime with
  `paused=True`, call `_runtime_gates()`; observed output: `(True, False, False)`.
- Stop criterion: do not use control-API pause as a safety control; do not begin P6 or
  unsupervised paper operation until a production-path regression proves no intent and
  no fill while paused. Production worker-stop remains the documented restriction.

### B-FINDING-02 — Pending scheduled entries bypass later pause/kill/readiness

- Severity: **S2 High**
- Impact: an intent accepted at day close can still open a new paper position at next
  open after an operator pause/kill or later entry-readiness loss. Risk receives
  `ACTIVE`, so the final authorization cannot see the changed state.
- Confidence: **High**; the state is absent from the full fill interface/call chain.
- Soll: FREEZE blocks new entries (`docs/paper-trading-orchestrator-v1.md:33`).
- Ist: `FillProcessingContext` and `process_scheduled_intents_for_open` have no runtime
  gate (`lifecycle.py:103-115`, `:242-319`); risk adapter defaults ACTIVE
  (`backtester/paper_lifecycle.py:124-150`).
- Stop criterion: after pause, kill, or readiness loss, stop the worker before a due
  open; block P6/unsupervised operation until pending-entry negative tests pass for
  pause, kill, stale heartbeat and degraded state.

### B-FINDING-05 — Gap stop fill price contradicts frozen exact-open rule

- Severity: **S2 High** (wrong persisted PnL/economic evidence)
- Impact: every gap exit is worse than the frozen exact-open assumption by configured
  slippage, changing realized PnL, cash, fees and experiment/paper parity. It is
  conservative but still contractually wrong and makes comparisons ambiguous.
- Confidence: **High**.
- Soll: gap exit `Open` exactly (`docs/risk-specification.md:260-273`).
- Ist: gap trigger reference is open, then generic exit slippage changes fill price
  (`stops.py:261-267`; `paper_lifecycle.py:246-260`).
- Stop criterion: do not use affected paper results for P5/P6 parity or execution-decay
  decisions until the governing assumption is explicitly reconciled and tested.

### B-FINDING-07 — Partial-fill, cancel, and protective-order claims exceed behavior

- Severity: **S3 Medium**
- Impact: enums/schema and a misleading test name can create false confidence that
  partial fills resize stops/risk and that protective orders are persisted. Those
  behaviors are absent; this is especially dangerous if paper evidence is later used
  as a live-readiness argument.
- Confidence: **High**.
- Soll: partial fill recalculates size/stop/risk; initial STOP_MARKET exists and trailing
  updates cancel-replace (`docs/risk-specification.md:240-251`, `:297`).
- Ist: one full entry fill with `remaining_quantity=0`, no cancel path, no stop order
  (`execution.py:358-390`; repository-wide search).
- Stop criterion: explicitly label these features unimplemented; do not claim Phase-10
  coverage or advance any live/P8 execution design based on the current test.

### B-FINDING-08 — Unlock-before-STOPPED permits successor runtime-state clobber

- Severity: **S2 High**
- Impact: during rolling overlap, the old worker can release ownership, a successor can
  acquire and begin recovery, and the old worker can then overwrite the singleton
  runtime status to STOPPED. Scheduled fills are not themselves performed after
  unlock, but readiness/state can become false or stale and due fill behavior becomes
  timing-dependent.
- Confidence: **Medium**; exact interleaving is code-reachable but no two-process
  database reproduction was run.
- Evidence: unlock `application.py:355-356`, later STOPPED write `:358-362`; version
  check is local object comparison `repository.py:111-131`.
- Stop criterion: avoid overlapping/rolling worker starts; stop to zero and verify the
  predecessor is gone before starting the successor until a two-process regression
  proves atomic handoff.

## Tests actually executed

| Command | Duration | Result | Skips / boundary |
|---|---:|---|---|
| `python -m pytest tests/risk_engine -q` with audit worktree `services` on `PYTHONPATH` | 0.949 s | **50 passed** | none |
| Targeted paper unit suites for accounting, execution, readiness, runtime, scheduler, stops, production context and parity | 1.284 s | **35 passed** | PostgreSQL tests not included |
| Readonly API/dashboard-summary unit suites | 1.536 s | **15 passed**, 1 dependency deprecation warning | no database |
| `python -m ruff check services/risk_engine services/paper_trading tests/risk_engine` | 0.969 s | **pass** | none |
| Targeted PostgreSQL restart/lock/fill/recovery/pause/reconciliation suites | 5.909 s | **0 tests executed; 21 setup errors** | explicit local `paper_trading_test` authentication failed before setup; no pass claimed |

Tooling observed: Python 3.14.5. The repository's documented baseline is Python 3.12,
so these local unit results do not establish baseline-version parity.
