# Accounting and Reconciliation Audit — Auditor B

Independent scope: entry/exit economics, fees, slippage, funding, cash, realized and
unrealized PnL, equity, margin, snapshots, independent reconstruction, read API and
dashboard fields. Basis: Issue #371 at commit
`7b78eb9996eb16e6d2ec6a00c2e1908c518682d9`. No database or deployed runtime was
mutated or observed.

## Canonical accounting model

### Soll

- Equity = cash/account balance + mark-to-market unrealized PnL
  (`docs/risk-specification.md` §2).
- Canonical paper reconstruction uses ENTRY/EXIT fills, positions, and wallet, not
  audit-event payloads (`docs/paper-trading-orchestrator-v1.md:35`).
- Reconciliation mismatch must enter ERROR/freeze entries
  (`docs/risk-specification.md:292-298`).
- Funding is disabled in V1; it must not silently affect results
  (`services/paper_trading/config.py:102-109`).

### Code

Entry:

```text
entry fill price = open + configured adverse slippage
entry fee        = fill_price * quantity * fee_rate
cash delta       = -entry fee
margin_reserved  = fill notional / max_leverage
```

Evidence: `services/backtester/paper_lifecycle.py:87-105`, `:154-184` and
`services/paper_trading/execution.py:406-425`.

Exit:

```text
exit fill price  = exit reference - configured adverse slippage
gross PnL        = (exit fill - average entry) * quantity
exit fee         = exit fill notional * fee_rate
cash delta       = gross PnL - exit fee
realized PnL     = gross PnL - exit fee
```

Evidence: `services/backtester/paper_lifecycle.py:246-265` and
`services/paper_trading/stops.py:261-313`.

Entry fee is already removed from cash but not from `total_realized_pnl`; therefore
wallet cash after a complete round trip equals initial cash + exit gross PnL - both
entry and exit fees, while realized PnL stores exit gross PnL - exit fee. This is
internally consistent with current reconstruction (`accounting_verification.py:34-50`)
but means `total_realized_pnl` is not total net account profit after all fees. The
dashboard labels it “Realized PnL” and separately exposes total fees on the wallet
page; users must not interpret it as cash return.

## Accounting scenarios independently recalculated

The following deterministic scenarios use the code formulas, not a production DB.

| Scenario | Inputs | Expected economic result | Code/API treatment | Status |
|---|---|---|---|---|
| Entry only | Open 50,000; qty 0.1; 5 bps slippage; 5 bps fee | fill 50,025; fee 2.50125; cash 99,997.49875; margin 2,501.25; unrealized at entry mark 0 | entry transaction matches; position `unrealized_pnl` persists default 0 | `VERIFIED` at entry |
| Mark rises with open position | entry 50,000; qty 0.1; mark 60,000; cash 100,000 | unrealized +1,000; equity 101,000 | mark-aware pure function returns this, but production scheduled snapshots pass no marks and return 0/100,000 | `CONTRADICTED` — B-FINDING-04 |
| Non-gap stop | stop reference 48,000; qty 0.1; 5 bps slippage; fee 5 bps | fill 47,976; gross -202.4; fee 2.3988; wallet delta -204.7988 | generic exit accounting matches | `VERIFIED` for configured model |
| Gap below stop | open 47,000; same costs | frozen spec expects fill 47,000; code fill 46,976.5 | code adds 23.5 adverse slippage per unit | `CONTRADICTED` — B-FINDING-05 |
| Round trip reconstruction | one ENTRY + one EXIT | cash subtracts both fees and adds exit gross; fees sum both; realized adds exit gross - exit fee | reconstruction matches stored update formulas | `VERIFIED` statically |
| Funding disabled | `funding_enabled=False` | no event/cash effect; total_funding should remain zero | config rejects True; scheduler raises if invoked | `VERIFIED` fail-closed |
| Corrupted funding total | wallet `total_funding != 0`, no event | reconciliation should fail | verifier has no funding field/check | `CONTRADICTED` — B-FINDING-06 |
| Wallet cash corrupted after crash | fills/positions valid but wallet cash changed | startup must ERROR/freeze | standalone verifier detects; startup recovery does not call it and only checks wallet exists | `CONTRADICTED` — B-FINDING-03 |

Safe in-memory reproduction for the mark scenario, against this worktree's source:

```text
no_marks   equity=100000.0 unrealized=0.0
mark_60000 equity=101000.0 unrealized=1000.0
```

The production snapshot call at `services/paper_trading/scheduler.py:486-493` supplies
no `day_candles` or `prior_closes`. `PortfolioSnapshotService` converts missing inputs
to empty dictionaries (`portfolio.py:48-56`), and the mark resolver falls back to the
entry price (`services/backtester/portfolio.py:23-43`). Therefore all scheduled
snapshots with open positions report zero unrealized PnL unless a caller explicitly
provides marks; no production caller does. Position rows similarly default unrealized
PnL to zero (`paper_trading/db/orm.py:209-215`) and no open-position update path was
found.

## Persistence and independent reconstruction

| Check | Implementation | Assessment |
|---|---|---|
| Entry economic atomicity | order/fill/wallet/position/intent in one transaction (`execution.py:357-443`) | `VERIFIED` statically |
| Exit economic atomicity | EXIT fill/wallet/position in one transaction (`stops.py:269-326`) | `VERIFIED` statically |
| Cash reconstruction | seed cash - entry fees + exit gross - exit fees (`accounting_verification.py:21-50`) | `VERIFIED` formula |
| Fee reconstruction | sums all fill fees (`accounting_verification.py:34-36`) | `VERIFIED` |
| Slippage reconstruction | sums persisted fill slippage (`accounting_verification.py:34-36`) | `VERIFIED` total only; does not independently recompute from references/rates |
| Realized PnL | recomputed from exit fill and entry price (`accounting_verification.py:47-50`, `:120-137`) | `VERIFIED` |
| Exit-fill uniqueness | one EXIT fill per position checked (`accounting_verification.py:94-106`) | `VERIFIED` code; DB run unavailable |
| Closed margin | must be zero (`accounting_verification.py:108-119`) | `VERIFIED` code |
| Open margin | only checks positive (`accounting_verification.py:138-139`) | `PARTIALLY_VERIFIED`; does not recompute notional/leverage |
| Funding | omitted from `ReconstructedWallet` and comparison (`accounting_verification.py:12-59`, `:62-140`) | `CONTRADICTED` |
| Startup enforcement | recovery runs structural checks only (`recovery.py:84-93`) | `CONTRADICTED` |

The independent verifier also silently skips an EXIT fill with an unknown/missing
position during reconstruction (`accounting_verification.py:42-46`), then later reports
missing `position_id` only when the ID is null (`:94-106`). A non-null orphan ID should
normally be prevented by the foreign key, but the verifier itself does not emit a
specific issue for an unresolved referenced position. Database constraints are thus
part of its trust boundary.

## API and dashboard economic contract

### API

- `/api/v1/wallet` returns cash, realized PnL, total fees, total funding and total
  slippage as decimal strings (`services/paper_trading/readonly_api.py:314-330`).
- `/api/v1/positions` returns persisted position `unrealized_pnl`, which is not
  mark-refreshed in production (`readonly_api.py:333-371`; `api_models.py:112-128`).
- `/api/v1/equity` returns persisted snapshot cash/equity/unrealized/realized/open risk
  (`readonly_api.py:609-654`). The serialization is correct; source economics are not.
- `/api/v1/dashboard-summary` exposes only cash and realized PnL for wallet summary and
  persisted unrealized PnL for positions (`readonly_api.py:238-294`).

### Dashboard

- TypeScript `WalletResponse` declares cash, realized PnL and fees, but omits API fields
  `total_funding`, `total_slippage`, `wallet_id`, and `version`
  (`src/lib/paper-api/client.ts:57-62`). Runtime JSON still contains them, and the wallet
  page renders `Object.entries(wallet)`, so they currently appear despite the incomplete
  type (`src/app/dashboard/wallet/page.tsx:3-16`). This is fragile contract drift.
- `FillItem` omits `fee`, `slippage`, `market_open_price`, order/position IDs and the
  deterministic key (`client.ts:75-82`); the fills page displays only kind, symbol,
  quantity, fill price and time (`src/app/dashboard/fills/page.tsx:4-13`). Operators
  cannot independently inspect fee/slippage economics from that page.
- The overview correctly labels cash and wallet realized PnL rather than equity
  (`src/lib/dashboard/view-model.ts:54-87`) and streams a separate equity chart. The
  chart consumes the economically incorrect persisted snapshots described above.

Status: API serialization is `VERIFIED`; dashboard/API economic observability is
`PARTIALLY_VERIFIED`; mark-to-market values are `CONTRADICTED`.

## Reconciliation/readiness/incident assessment

- The daily reconciliation runbook invokes the standalone accounting script and treats
  failure as S2 + worker stop (`docs/runbooks/reconciliation-daily.md`). That manual path
  is sound as an operational restriction.
- Startup recovery does not automatically run the same check, despite service docs
  saying manual wallet mismatch requires intervention. A structurally valid fill chain
  only requires that a wallet exists (`recovery.py:143-163`).
- Readiness checks runtime, database, schema, advisory lock, scheduler, recovery,
  orphans, configuration failures and heartbeat (`readiness.py:173-218`), but no
  accounting-reconciliation flag/result.
- The tabletop duplicate-fill incident is simulated and cites the manual verifier; it
  is not evidence that deployed reconciliation automation or alerting is active.
- P6 daily archive/soak is not started per ROADMAP; no runtime reconciliation record was
  inspected.

## Candidate findings

### B-FINDING-03 — Startup recovery can reach READY with wallet mismatch

- Severity: **S2 High**
- Impact: corrupted cash/fees/realized totals can survive restart, while later entry
  sizing uses the bad wallet as equity/margin input. Dashboard and risk decisions can be
  wrong even though structural recovery reports READY.
- Confidence: **High** from complete recovery call graph; deployed occurrence not
  observed.
- Soll: mismatch => ERROR/freeze (`docs/risk-specification.md:298`).
- Ist: recovery check list excludes `verify_accounting_independent`
  (`recovery.py:84-93`); wallet-chain check only tests existence (`:143-163`).
- Reproduction requirement for remediation: in local test DB, create a valid fill/
  position chain, alter wallet cash in a transaction, restart recovery, and assert
  FAILED/DEGRADED with entry readiness false. This audit did not mutate a DB to do so.
- Stop criterion: after any uncertain crash/restart or reconciliation mismatch, stop the
  worker and run the external reconciliation before restart; block P6 and unsupervised
  paper until recovery/readiness consumes a sealed reconciliation result.

### B-FINDING-04 — Production equity and unrealized PnL snapshots are unmarked

- Severity: **S2 High**
- Impact: open-position unrealized PnL is shown as zero and equity as cash in API/
  dashboard history. This invalidates economic monitoring, drawdown interpretation,
  daily reconciliation/soak evidence and execution-decay comparisons.
- Confidence: **High**, static full caller search plus safe pure-function reproduction.
- Soll: equity = cash + mark-to-market unrealized PnL.
- Ist: production snapshot callers pass no marks (`scheduler.py:486-493`,
  `stops.py:160-164`), missing marks fall back to entry (`backtester/portfolio.py:34-43`),
  open position PnL column is never refreshed.
- Stop criterion: do not begin P6 or rely on dashboard equity/PnL while any position is
  open; require mark-provenance tests through DB→API→dashboard before economic sign-off.

### B-FINDING-06 — Independent reconciliation omits funding integrity

- Severity: **S2 High** under the project's “wrong PnL” definition; current exposure is
  reduced because funding is fail-closed disabled.
- Impact: a nonzero/corrupt wallet funding total can be served by API/dashboard while
  `verify_accounting_independent` returns no funding issue. Future funding activation
  would have no independent event-to-wallet proof.
- Confidence: **High**.
- Soll: current V1 funding is zero/N/A; later funding must reconcile to events.
- Ist: `ReconstructedWallet` has no funding field and verifier never compares
  `wallet.total_funding` (`accounting_verification.py:12-59`, `:62-140`).
- Stop criterion: keep `funding_enabled=False`; block any P6 claim that funding is
  observed/reconciled and block future activation until zero/event equality has a
  negative test.

B-FINDING-05 (gap-exit slippage) is defined in
`RISK_AND_EXECUTION_AUDIT.md` because it is both an execution and accounting
contract break.

## Tests actually executed

| Command | Duration | Result | Accounting meaning |
|---|---:|---|---|
| Targeted paper unit suites including accounting/stops/execution | 1.284 s | **35 passed** | pure formulas and present unit assertions only |
| `python -m pytest tests/paper_trading/test_readonly_api.py tests/paper_trading/test_dashboard_summary_api.py tests/paper_trading/test_api_read.py -q` | 1.536 s | **15 passed**, 1 dependency warning | serialization/summary contract, no DB |
| `npm run test:unit -- --run` | 2.096 s | **20 files / 163 tests passed** | 31 dashboard formatter/view-model tests; no real API/DB economic chain |
| Targeted PostgreSQL accounting/restart/lock/fill/recovery suites | 5.909 s | **0 executed; 21 setup errors** | local test-role authentication failure; no DB result claimed |

Not checked: deployed database values, live API responses, dashboard rendering with a
real open position, Railway reconciliation logs, funding events, daily archive, or
exchange reconciliation (live is out of scope).
