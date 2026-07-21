# Executive System Audit Summary

**Audit issue:** [#371](https://github.com/Pain1234/save-money-trading-bot/issues/371)
**Audit window:** `2026-07-19T16:52:07.7739084Z` to `2026-07-19T18:37:03.021Z`
**Audited `origin/main`:** `7b78eb9996eb16e6d2ec6a00c2e1908c518682d9`
**Final phase decision:** **`BLOCK_P5`**
**Additional operating restriction:** no P6/unsupervised Paper operation until its P1 safety
findings are closed. This is not `STOP_ALL_EXECUTION`: no P0, live implementation, wallet
signing, real order path, active duplicate writer or holdout opening was found.

## Result in one paragraph

The repository has a substantial, mostly green offline test base and several sound boundaries:
Strategy does not directly place orders, Public Core contains no live/wallet path, normal Risk
limits are well tested, Monitor GET behavior is read-only, and the audit did not touch P5.
However, the frozen Strategy exit contract, effective configuration identity, data provenance,
experiment invalidation, final Paper entry gates, startup reconciliation, open-position economics,
Research backend authorization and Python deployment reproducibility are contradicted by code or
safe negative reproductions. Runtime SHAs, actual worker ownership, deployed database identity and
private P5 state were unavailable and therefore are not asserted. Fourteen evidenced P1 findings
make continuation to P5 unacceptable without remediation and a new independent verification.

## Scope and evidence

### Services checked

`strategy_engine`, `risk_engine`, `backtester`, `market_data`, `paper_trading`, `research`,
`trading_constraints`, Paper worker, Paper/Research API, and Next.js Dashboard.

### Deployment identities checked

| Service | Expected audit SHA | Running SHA/image | Result |
|---|---|---|---|
| Dashboard | `7b78eb9…` | NOT_VERIFIABLE | Public login observed; no safe build metadata. |
| Paper/Research API | `7b78eb9…` | NOT_VERIFIABLE | Private service/network unavailable. |
| Paper worker | `7b78eb9…` | NOT_VERIFIABLE | Logs, replica count and lock owner unavailable. |
| Repository CI | `7b78eb9…` | Full CI run `29695342023` | All substantive jobs successful. |

The public root redirected to `https://bot.save-money.xyz/login?next=%2Fdashboard` and described a
read-only Paper monitor. No credentials were entered. This proves reachability only, not service
commit parity.

### Source material checked

`AGENTS.md`, `README.md`, `ROADMAP.md`, changelog structure, architecture, decision log and relevant
ADRs, risk register, Definition of Done, project operating system/management docs, Strategy/Risk
specifications and frozen inventory, Market Data contract/P3 audit, Paper architecture/runbooks,
Research identity/artifact/reproducibility/gates/scorecards/regime/validation documents, P4/P5
status and public/private contracts, deployment/backup/security runbooks, Docker/Railway/CI configs,
service READMEs, implementation and tests. Private repository contents and private metrics were not
read.

## Test execution

| Command/scope | Duration | Result | Interpretation |
|---|---:|---|---|
| `git diff --check` at initial checkout | <1 s | Failed on CRLF/LF drift in three pre-existing spec blobs | Repository checkout hygiene, not an Audit-doc defect. |
| Python 3.12 `ruff check .` | recorded in inventory | Passed | Static lint green. |
| Python 3.12 `mypy .` | short | Failed: 3 script/import/module-discovery errors | Mandatory documented command not green. |
| Configured packages with `MYPYPATH=services`, `python -m mypy` | 7.9 s | 35 errors in 17 files | Product package type gate also not green. |
| `pytest tests/ -q` | 146.4 s | 1,444 passed, 35 failed, 8 skipped, 29 subtests passed | Not a valid product verdict: shared DB was concurrently downgraded to migration 010; soak env absent; Windows npm subprocess mismatch. |
| CI-shaped non-DB suite | 65.96 s | 1,283 passed, 1 skipped, 171 deselected, 29 subtests | Clean core evidence. |
| Research/Paper/Risk/Strategy isolated target | 66.10 s | 804 passed, 1 skipped, 156 deselected | Clean four-area evidence. |
| Auditor A offline/synthetic scopes | recorded | 578 passed, 1 skipped | Data/Strategy/Research positives and adversarial probes. |
| Market Data suite | recorded | 172 passed | Positive/offline coverage; DB teardown invalidated later DB state. |
| Auditor B Risk/Paper/API scopes | 0.9–1.5 s each | 50 + 35 + 15 passed | Unit/API behavior; no valid shared-DB claim. |
| Auditor C API/Security/Artifact | 8.78 s | 75 passed, 1 skipped | API/artifact normal and negative behavior. |
| Auditor C safe resilience | 0.44 s | 24 passed, 14 deselected | Non-destructive resilience evidence. |
| `npm run test:unit` | 1.56–2.10 s | 20 files, 163 passed | Dashboard unit evidence. |
| `npm run build` | 25.81 s | Passed, 12 static pages | Cross-worktree ESLint warning; clean exact-SHA CI build also green. |
| `npm run test:research-smoke` | 6.9 s | 10 passed | Stub/browser smoke only; warns standalone build should use standalone server. |
| Exact-SHA Full CI `29695342023` | remote | All substantive jobs passed | Clean CI evidence for frozen SHA, not deployed-runtime identity. |

`npm ci` installed 413 packages and reported two moderate advisories without changing the lockfile.
A separate `npm audit --omit=dev` was not executed because the environment rejected disclosure of
the private workspace dependency graph to an external registry. No advisory package identity is
therefore claimed.

### Tests not validly executable in this audit

- PostgreSQL restart/lock/reconciliation/catalog negatives: the shared local test database was
  changed by concurrent teardown (`010` versus repository head `011`) and later authentication
  failed. It was not repaired or reset because this was audit-only.
- Worker A/Worker B hard-crash proof: requires a clean isolated Paper database/process harness.
- Railway private networking, replica, log, DB and authenticated UI checks: no authorization/data.
- Live/Hyperliquid private, wallet and order tests: prohibited and out of scope.
- P5 execution/holdout tests: prohibited; none invoked.
- Soak/P6: environment absent and phase is not approved by this audit.

## Finding count

| Severity | Count |
|---|---:|
| P0 | 0 |
| P1 | 14 |
| P2 | 10 |
| P3 | 1 |
| INFO | 3 |

Full, stable records are in `FINDINGS_REGISTER.md`.

## Ten most important findings

1. `AUD-P1-006/-007`: persisted pause is ignored by the production intent gate, and already
   scheduled entries bypass later pause/kill/readiness before fill.
2. `AUD-P1-008`: startup can report READY without consuming independent wallet/accounting
   reconciliation.
3. `AUD-P1-009`: open-position production snapshots return unrealized PnL zero and equity=cash
   because marks are omitted.
4. `AUD-P1-001`: the frozen Monthly-regime exit is not executable.
5. `AUD-P1-002`: unknown parameters are bound into Research identity but silently ignored at
   execution.
6. `AUD-P1-004`: invalidated experiment evidence can be reactivated through registry append or
   reconstruction.
7. `AUD-P1-005`: PostgreSQL raw Dataset ID collision does not verify content identity.
8. `AUD-P1-013`: Research mutations are mounted into the combined backend without backend auth;
   runtime network isolation is unverified.
9. `AUD-P1-014`: Python production rebuilds resolve unpinned dependencies, so equal Git SHA does
   not imply equal executable behavior.
10. `AUD-P1-003/-010`: Paper higher-timeframe provenance and gap-fill pricing contradict the
    Research/frozen parity contracts.

## Invariant decisions

### Confirmed

- Strategy emits intents and has no direct wallet/live-order path.
- Public Core contains no wallet signing or live-order implementation found by the audit.
- No automatic Research→Paper/Live promotion path was found.
- Declared Strategy defaults and core Risk numeric boundaries match their inventories.
- Same declared valid input is deterministic in the covered Strategy/Research paths.
- Monitor browser/API GET paths are read-only; disabled control API is not mounted there.
- Artifact endpoint normal path enforces canonical path, allow-list, size and checksum controls.
- The audit opened no P5 holdout, sent no order and changed no frozen parameter.

### Disproved

- Strategy V1 exactly implements every frozen exit.
- Dataset/Run identity is fail-closed across the PostgreSQL raw catalog.
- Backtest and production-style Paper use fully equivalent higher-timeframe/economic assumptions.
- Pause, kill and later readiness loss always prevent new Paper risk.
- Startup reconciliation necessarily blocks READY on economic corruption.
- Dashboard/API open-position equity and unrealized PnL reflect market marks.
- Invalidated Research evidence remains invalidated on all resolution paths.
- Research is end-to-end read-only.
- Same Git SHA guarantees the same Python deployment dependency set.
- UI always distinguishes zero, missing and incident semantics.

### Not verifiable

- Exactly one active deployed Execution Owner, advisory-lock holder and worker replica.
- Running Dashboard/API/worker SHA, image digest, Railway revision and shared DB identity.
- Deployed logs, incidents, recovery state and authenticated Dashboard values.
- Actual private Research/P5 artifact seals, ACLs, execution state and metrics.
- Clean PostgreSQL two-process restart/reconciliation behavior at the frozen SHA.

## Area conclusions

### Strategy, data and parity

Core deterministic calculations and many validators are green, but Strategy V1 is not fully
contract-conformant. Unknown configuration keys, Monthly exit absence, higher-timeframe provenance
and gap pricing prevent credible end-to-end parity. Data/Candles are **partially trustworthy**, not
trustworthy enough for new P5 evidence.

### Risk and execution

Risk Engine boundary formulas are well covered in isolation. The production Paper orchestration
around them is not safe for unsupervised use because pause and final fill authorization diverge,
and worker handover has an untested fencing race. Exactly one deployed owner is NOT_VERIFIABLE.

### Accounting and reconciliation

Closed-trade unit formulas/fee application are largely coherent. Open-position equity is wrong in
production snapshots, startup readiness is not bound to independent accounting, and funding is
not independently checked. Database/API/Dashboard economic equality was not validly demonstrated.

### Research and scorecards

Pin/checksum/gate tests are strong for normal inputs. Effective config identity, invalidation and
backend mutation authority break the evidence trust chain. No real public complete chain from
ExperimentSpec to Validation Study was available; private evidence was intentionally excluded.

### UI/API semantics

Monitor GET behavior and most formatters are sound. Research is not end-to-end read-only,
zero-failure/missing semantics are confused, incident fallback is misleading, and execution-owner
state is absent. Authenticated production screens were not observed.

### Deployment and security

Exact-SHA CI is green and the public login is reachable. Running identities are unknown and the
Python image is not dependency-locked. No secret/wallet key was identified or printed. Artifact
access is comparatively strong; audit-event nested redaction and Research backend auth are gaps.

### P5 holdout status

The audit did not touch Holdout C or execute #204/#205/#251-#254. Public metadata describes the
holdout as sealed/blocked, while two public P5 status documents contradict each other about policy
sign-off and #251-#254. The actual private state remains **NOT_VERIFIABLE** and no private value is
included here.

## Phase decision rationale

`BLOCK_P5` follows directly from hard P1 findings affecting the Strategy contract, dataset/config
identity, invalidation, Research mutation boundary and executable deployment identity. It is not a
score. In parallel, Paper/P6 remains restricted because final entry gating, startup reconciliation,
equity snapshots and worker handover are unsafe or unproven. The remediation order and proposed
issue map are in `REMEDIATION_PLAN.md`; no finding issue may be created until human approval.

## Audit boundary confirmation

- No live order sent.
- No wallet signature or credential use.
- No Strategy or Risk parameter changed.
- No market activated.
- No production configuration/data mutation, migration, deletion or fallback added.
- No P5 execution or Holdout opening.
- No existing Research artifact retroactively modified.
- No private P5 metric or secret published.
- No unevidenced candidate represented as confirmed; runtime unknowns remain NOT_VERIFIABLE.
