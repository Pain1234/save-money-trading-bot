# Risk Register

Initial catalog of known and anticipated risks. **Do not mark mitigations as implemented unless evidenced in code/docs.**

Legend — **Status:** `open` | `planned` | `partial` | `closed`

Severity: qualitative **Impact** × **Likelihood** → register **Severity** (critical/high/medium/low)

---

| Risk-ID | Description | Category | Likelihood | Impact | Severity | Early detection | Mitigation | Owner area | Status | Issue |
|---------|-------------|----------|------------|--------|----------|-----------------|------------|------------|--------|-------|
| R-001 | Stale or gap-filled market data leads to wrong evaluations | Marktdaten | Medium | High | High | Missing candles, reconnect logs, readiness DEGRADED | ISO weekly derivation; reconnect hardening; P3 versioning | market_data | partial | — |
| R-002 | Backtest optimistic vs paper/live (fills, fees, funding) | Paper-to-Live-Decay | High | High | Critical | PnL drift vs backtest | Document cost model; P6 soak measurement | research / paper | open | — |
| R-003 | Strategy overfitting on in-sample tuning | Strategie-Overfitting | Medium | High | High | OOS degradation | P5 untouched OOS; walk-forward; reject criteria | research | open | — |
| R-004 | Look-ahead or parity bug between backtester and paper | Backtest-Bias | Low | High | High | Parity tests, E2E replay | Phase 9 tests; regression suite | backtester / paper | partial | — |
| R-005 | Incorrect fee/slippage assumptions in research | Kostenmodell | Medium | Medium | Medium | Stress tests in P5 | Document assumptions per experiment | research | open | — |
| R-006 | Duplicate fills or orders on worker restart | Execution | Low | Critical | Critical | Recovery checks, advisory lock | `lock.py`, `recovery.py`, idempotency tests | paper_trading | partial | — |
| R-007 | Wallet/position/fill chain inconsistency | Accounting | Low | Critical | Critical | Startup recovery fatal errors | Recovery policy fatal cases; manual intervention path | paper_trading | partial | — |
| R-008 | Single worker ops mistake (double deploy) | Execution | Medium | High | High | Heartbeat, advisory lock contention | Exactly 1 replica documented; lock blocking | infrastructure | partial | — |
| R-009 | PostgreSQL data loss without tested backup | Infrastruktur | Low | Critical | Critical | Backup age monitoring | P2 backup/restore runbook and test | infrastructure | open | — |
| R-010 | Exchange API outage or breaking change | Exchange | Medium | Medium | Medium | WS disconnect rate, DEGRADED state | Reconnect + degraded mode; soak incidents | market_data | partial | — |
| R-011 | Dashboard or API credential exposure | Security | Low | High | High | Secret scanning, architecture review | Private API URL; no DB in browser | dashboard | partial | — |
| R-012 | Unauthorized live trading activation | Security / Kapital | Low | Critical | Critical | Code review, governance labels | Live not implemented; P8 gate + human approval | governance | partial | — |
| R-013 | Risk limit bypass or kill switch failure | Kapital und Drawdown | Low | Critical | Critical | Control API tests, audit log | FREEZE kill switch; spec in risk-specification | risk_engine | partial | — |
| R-014 | Parameter change without documentation | Strategie-Overfitting | Medium | High | High | Diff review, AGENTS.md | P0 parameter freeze issue; governance | governance | planned | — |
| R-015 | Research results overwritten or unversioned | Backtest-Bias | Medium | Medium | Medium | Missing experiment-ID | Experiment template; invalidation label | research | planned | — |
| R-016 | Human misconfiguration on Railway deploy | menschliche Fehlbedienung | Medium | High | High | Deploy checklist | `docs/railway-paper-trading-dashboard-v1.md`, runbooks | infrastructure | partial | — |
| R-017 | Bulk test flakiness hides real regressions | Infrastruktur | Medium | Medium | Medium | CI signal (when added) | Document known postgres isolation failures; fix suite | engineering | open | — |
| R-018 | Correlated “new strategies” add no diversification | Strategie-Overfitting | Medium | Medium | Medium | Correlation matrix in P7 | Independent hypothesis requirement | research | open | — |

---

## Review cadence

- **P0 exit:** Validate register against architecture doc; link top 5 risks to GitHub issues.
- **Each phase exit:** Re-score risks; close or downgrade only with evidence.
- **After S1/S2 incident:** Add or update row; link incident doc.

---

## Adding a risk

1. Assign next `R-NNN`.
2. Open GitHub issue with label `area:governance` or relevant area.
3. Reference issue in the table.
4. Never claim `closed` without verification artifact (test, runbook execution, deploy proof).
