# Risk Register

Initial catalog of known and anticipated risks. **Do not mark mitigations as implemented unless evidenced in code/docs.**

Legend — **Status:** `open` | `planned` | `partial` | `closed`

Severity: qualitative **Impact** × **Likelihood** → register **Severity** (critical/high/medium/low)

---

| Risk-ID | Description | Category | Likelihood | Impact | Severity | Early detection | Mitigation | Owner area | Status | Issue |
|---------|-------------|----------|------------|--------|----------|-----------------|------------|------------|--------|-------|
| R-001 | Stale or gap-filled market data leads to wrong evaluations | Marktdaten | Medium | High | High | Missing candles, reconnect logs, readiness DEGRADED | ISO weekly derivation; reconnect hardening; P3 versioning | market_data | partial | [#45](https://github.com/Pain1234/save-money-trading-bot/issues/45) |
| R-002 | Backtest optimistic vs paper/live (fills, fees, funding) | Paper-to-Live-Decay | High | High | Critical | PnL drift vs backtest | Document cost model; P6 soak measurement | research / paper | open | [#46](https://github.com/Pain1234/save-money-trading-bot/issues/46) |
| R-003 | Strategy overfitting on in-sample tuning | Strategie-Overfitting | Medium | High | High | OOS degradation | P5 untouched OOS; walk-forward; reject criteria | research | open | [#47](https://github.com/Pain1234/save-money-trading-bot/issues/47) |
| R-004 | Look-ahead or parity bug between backtester and paper | Backtest-Bias | Low | High | High | Parity tests, E2E replay | Phase 9 tests; regression suite | backtester / paper | partial | [#48](https://github.com/Pain1234/save-money-trading-bot/issues/48) |
| R-005 | Incorrect fee/slippage assumptions in research | Kostenmodell | Medium | Medium | Medium | Stress tests in P5 | Document assumptions per experiment | research | open | [#49](https://github.com/Pain1234/save-money-trading-bot/issues/49) |
| R-006 | Duplicate fills or orders on worker restart | Execution | Low | Critical | Critical | Recovery checks, advisory lock | `lock.py`, `recovery.py`, idempotency tests; [`docs/operations/idempotency-audit.md`](operations/idempotency-audit.md), [`docs/runbooks/worker-restart.md`](runbooks/worker-restart.md) | paper_trading | partial | [#14](https://github.com/Pain1234/save-money-trading-bot/issues/14) |
| R-007 | Wallet/position/fill chain inconsistency | Accounting | Low | Critical | Critical | Startup recovery fatal errors; weekly reconciliation | Recovery policy fatal cases; [`docs/runbooks/reconciliation-daily.md`](runbooks/reconciliation-daily.md) | paper_trading | partial | [#12](https://github.com/Pain1234/save-money-trading-bot/issues/12) |
| R-008 | Single worker ops mistake (double deploy) | Execution | Medium | High | High | Heartbeat, advisory lock contention | Exactly 1 replica documented; lock blocking | infrastructure | partial | — |
| R-009 | PostgreSQL data loss without tested backup | Infrastruktur | Low | Critical | Critical | Backup age monitoring | [`docs/runbooks/backup-restore.md`](runbooks/backup-restore.md) - local restore drill with committed data 2026-07-14; Railway non-prod restore open | infrastructure | partial | [#11](https://github.com/Pain1234/save-money-trading-bot/issues/11) |
| R-010 | Exchange API outage or breaking change | Exchange | Medium | Medium | Medium | WS disconnect rate, DEGRADED state | Reconnect + degraded mode; soak incidents | market_data | partial | — |
| R-011 | Dashboard or API credential exposure | Security | Low | High | High | Secret scanning, architecture review | Private API URL; no DB in browser | dashboard | partial | — |
| R-012 | Unauthorized live trading activation | Security / Kapital | Low | Critical | Critical | Code review, governance labels | Live not implemented; P8 gate + human approval | governance | partial | — |
| R-013 | Risk limit bypass or kill switch failure | Kapital und Drawdown | Low | Critical | Critical | Control API tests, audit log | FREEZE kill switch; spec in risk-specification | risk_engine | partial | — |
| R-014 | Parameter change without documentation | Strategie-Overfitting | Medium | High | High | Diff review, AGENTS.md | Parameter inventory + ADR-009; governance | governance | partial | [#4](https://github.com/Pain1234/save-money-trading-bot/issues/4) |
| R-015 | Research results overwritten or unversioned | Backtest-Bias | Medium | Medium | Medium | Missing experiment-ID | Experiment template; invalidation label | research | planned | — |
| R-016 | Human misconfiguration on Railway deploy | menschliche Fehlbedienung | Medium | High | High | Deploy checklist | `docs/railway-paper-trading-dashboard-v1.md`, runbooks | infrastructure | partial | — |
| R-017 | Bulk test flakiness hides real regressions | Infrastruktur | Medium | Medium | Medium | CI signal (when added) | Document known postgres isolation failures; fix suite | engineering | open | — |
| R-018 | Correlated multi-asset exposure adds no real diversification | Strategie-Overfitting | Medium | Medium | Medium | Correlation matrix in P7 | Independent hypothesis + cluster risk budget; ADR-014 asset profiles | research / risk | open | TBD |
| R-019 | Dashboard latency masks critical status changes | Monitoring | Medium | High | High | Slow page loads, stale heartbeat not visible | P2.5 performance baseline and production acceptance | dashboard | open | TBD |
| R-020 | Growing history tables slow unindexed dashboard queries | Infrastruktur | Medium | Medium | Medium | Rising p95 on table endpoints | P2.5 SQL/index audit with `EXPLAIN ANALYZE` | dashboard / infrastructure | open | TBD |
| R-021 | Uncontrolled caching shows stale readiness or warnings | Monitoring | Medium | High | High | READY shown while worker degraded | P2.5 documented cache policy with revalidation tests | dashboard | open | TBD |
| R-022 | More assets create apparent diversification while risk stays correlated | Kapital und Drawdown | Medium | High | High | Cluster drawdown in shadow/paper | P7 correlated exposure model; cluster risk limits | risk / research | open | TBD |
| R-023 | HIP-3 equity perps carry distinct funding, oracle, and liquidity risks | Marktdaten | Medium | High | High | Funding/oracle divergence vs crypto | P7B asset profile; HIP-3 validation requirements | research / market_data | open | TBD |
| R-024 | Synthetic equity perps misinterpreted as real stock ownership | Governance | Low | Medium | Medium | Documentation review | ADR-014 wording; no "stock holding" claims in UI/docs | governance | open | TBD |

---

## Review cadence

- **P0 exit:** Top 5 risks (R-001–R-005) linked to GitHub issues ([#45](https://github.com/Pain1234/save-money-trading-bot/issues/45)–[#49](https://github.com/Pain1234/save-money-trading-bot/issues/49)); verified 2026-07-13 (Issue #6).
- **Each phase exit:** Re-score risks; close or downgrade only with evidence.
- **After S1/S2 incident:** Add or update row; link incident doc.

---

## Top-5 tracking (R-001–R-005)

| Risk-ID | Status | Issue | Notes |
|---------|--------|-------|-------|
| R-001 | partial | #45 | Reconnect + ISO weekly in place; P3 manifests not started |
| R-002 | open | #46 | P6 soak not started; cost model documented in specs only |
| R-003 | open | #47 | P5 OOS discipline not started |
| R-004 | partial | #48 | Shared engines + test suites; formal parity audit open |
| R-005 | open | #49 | P4 experiment template exists; enforcement not started |

---

## Adding a risk

1. Assign next `R-NNN`.
2. Open GitHub issue with label `area:governance` or relevant area.
3. Reference issue in the table.
4. Never claim `closed` without verification artifact (test, runbook execution, deploy proof).
