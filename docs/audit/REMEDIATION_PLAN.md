# Proposed Remediation Plan

This is a proposal for human review under [Issue #371](https://github.com/Pain1234/save-money-trading-bot/issues/371).
It creates no issue, changes no production behavior, changes no frozen parameter, and does not
open P5. Each accepted remediation must receive its own scoped issue/branch/PR, regression
evidence and human merge decision.

## Immediate restrictions (no code change)

1. Keep P5 evidence acceptance and Holdout C blocked.
2. Do not begin P6 or unsupervised Paper operation.
3. Do not treat control-API pause as a safety barrier; for an unsafe state, stop the worker
   before the next due Open and verify it has exited.
4. Do not use rolling/overlapping worker starts; scale to zero, verify predecessor exit, then
   start the successor.
5. Do not rely on Dashboard equity/unrealized PnL while a position is open.
6. Keep funding disabled.
7. Permit monitoring GETs only; do not perform P5/final Research mutations until the backend
   write/auth/network contract is approved and verified.
8. Do not use a rebuilt Python image or affected Research/Paper artifacts as promotion evidence
   without immutable dependency/image provenance.

## Recommended order

### Wave 1 — Contain evidence-integrity failures

- `AUD-P1-004`: make invalidation binding and audit existing registry state.
- `AUD-P1-005`: reject raw Dataset ID/hash conflicts atomically and verify stored catalog rows.
- `AUD-P1-002`: reject unknown parameters and bind identity to effective configuration.
- `AUD-P1-013`: decide Research write-plane contract, add backend authorization/isolation proof.
- `AUD-P1-014`: make Python image builds dependency-reproducible and publish immutable provenance.

Reason: later tests or phase evidence are not trustworthy until identity, invalidation, mutation
authority and executable image identity are trustworthy.

### Wave 2 — Close final-entry and ownership gates

- `AUD-P1-006` and `AUD-P1-007`: one authoritative fail-closed entry authorization at intent
  creation and immediately before fill.
- `AUD-P1-008`: bind independent reconciliation to startup/readiness.
- `AUD-P1-012`: implement fenced, atomic worker handover.
- `AUD-P2-007`: expose safe authenticated owner/fencing status for operations.

Reason: these are the hard barriers against opening new risk in unknown state.

### Wave 3 — Restore Strategy/Data/Accounting parity

- Human decisions first for `AUD-P1-001` and `AUD-P1-010`; frozen specs must not be silently
  rewritten to match code.
- `AUD-P1-003`: unify higher-timeframe provenance/conflict handling.
- `AUD-P1-009`: mark-to-market snapshot provenance through DB→API→Dashboard.
- `AUD-P1-011`: reconcile funding zero/event equality while it remains disabled.
- Re-run Strategy→Backtester→Paper adversarial parity and independently calculated accounting.

### Wave 4 — Make failure evidence reliable

- `AUD-P2-010`: isolate every PostgreSQL suite by run/database/schema and remove destructive
  shared teardown behavior.
- `AUD-P2-009`: define one clean, CI-enforced mypy command and resolve its declared dependencies
  and source errors.
- Add the missing negative tests listed in `TEST_COVERAGE_GAPS.md`.
- Re-run exact full suite from a fresh Python 3.12/Node 22 environment and preserve raw logs.

### Wave 5 — Semantics, docs and operational clarity

- Address `AUD-P2-003` through `AUD-P2-008`, then `AUD-P2-001`, `AUD-P2-002` and
  `AUD-P3-001`.
- Reconcile the P5 status documents without accessing or disclosing private metrics.
- Update architecture only after implementation decisions are accepted.

## Proposed issue map

“New issue needed” means after human approval only. Related closed issues are context, not proof
that the newly observed behavior is already covered.

| Finding | Bestehendes Issue / related history | Neues Issue nötig | Priorität | Blockiert Phase |
|---|---|---|---|---|
| AUD-P1-001 | #4/#308 closed parameter freeze; #196 candidate freeze | Yes: Strategy exit contract decision | P1 | P5 |
| AUD-P1-002 | #163 closed dataset/run binding | Yes: effective-config identity | P1 | P5 |
| AUD-P1-003 | #81/#84 closed data quality/repro audit | Yes: HTF production parity | P1 | P5/P6 |
| AUD-P1-004 | #371 umbrella; no specific open issue found | Yes: binding invalidation | P1 | P5 |
| AUD-P1-005 | #79 closed catalog implementation | Yes: raw-ID collision safety | P1 | P5 |
| AUD-P1-006 | #371 umbrella | Yes, may share tightly scoped final-entry gate issue with -007 | P1 | P6 |
| AUD-P1-007 | #371 umbrella | Yes, same final-entry authorization program as -006 | P1 | P6 |
| AUD-P1-008 | #12/#316 closed reconciliation requirements; #258 open archive | Yes: startup economic readiness | P1 | P6 |
| AUD-P1-009 | #359 closed number/equity labels; #46 open execution decay | Yes: mark-to-market economic chain | P1 | P6 |
| AUD-P1-010 | #49 closed fee/slippage documentation; #46 open decay | Yes: governed gap-price decision | P1 | P5/P6 |
| AUD-P1-011 | #164 closed funding semantics | Yes: independent funding reconciliation | P1 | P6/future funding |
| AUD-P1-012 | #14/#318 closed restart test; #259 open incident handling | Yes: fenced worker handover | P1 | P6 |
| AUD-P1-013 | #238/#240 closed read-only UI/API work | Yes: Research backend authority | P1 | P5 |
| AUD-P1-014 | #371 umbrella | Yes: locked Python production image | P1 | P5/P6 promotion |
| AUD-P2-001 | #147 closed Research architecture | Yes: current architecture inventory | P2 | Documentation sign-off |
| AUD-P2-002 | #304/#305 open future StrategyIntent planning | Prefer update those only if scope matches; otherwise new | P2 | P8/live claims |
| AUD-P2-003 | #371 umbrella | Yes: safe deployment identity | P2 | Promotion verification |
| AUD-P2-004 | #357 closed safe artifact access (adjacent only) | Yes: audit-event redaction | P2 | Security sign-off |
| AUD-P2-005 | #371 umbrella | Yes: Research degraded write gate | P2 | P5 operations |
| AUD-P2-006 | #371 umbrella | Yes: validation zero/missing semantics | P2 | UI evidence sign-off |
| AUD-P2-007 | #14/#318 closed restart; #259 open incident handling | Update #259 if accepted, otherwise new observability issue | P2 | P6 operations |
| AUD-P2-008 | #196/#204/#205/#251-#254 | Update authoritative existing P5 issues/docs; no duplicate | P2 | P5 |
| AUD-P2-009 | #371 umbrella | Yes: reproducible static gate | P2 | Merge readiness |
| AUD-P2-010 | #371 umbrella | Yes: isolated PostgreSQL harness | P2 | DB safety evidence |
| AUD-P3-001 | #15/#22/#28/#35/#42 closed incident gaps; #259 open | Update #259 if scope accepted | P3 | No independent block |
| AUD-INFO-001 | #371 umbrella | Optional separate repository hygiene issue | INFO | Quality-gate clarity |
| AUD-INFO-002 | #371 umbrella | No; input for AUD-P2-003 | INFO | Runtime verification |
| AUD-INFO-003 | #204/#205 | No; retain existing blockers | INFO | P5 |

## Exit criteria before reconsidering `BLOCK_P5`

- All P1 findings affecting Strategy behavior, data/run identity, invalidation and Research
  mutation authority are closed with green negative regressions.
- A clean, isolated PostgreSQL full run proves catalog, restart, single-owner and reconciliation
  behavior.
- Strategy→Backtester→Paper parity includes adversarial higher-timeframe and gap cases.
- Same-SHA Python images have recorded locked dependency/image identity.
- Public P5 Source of Truth is internally consistent and human approval remains explicit.
- A new independent audit confirms the fixes; this audit must not be retroactively edited into a
  pass.

P6/unsupervised Paper additionally requires closure of pause/fill gates, startup reconciliation,
mark-to-market economics and worker handover even if P5 governance is handled separately.
