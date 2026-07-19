# Decision Log

Architecture and governance decisions in ADR style. Only **Accepted** entries below are evidenced by the current repository; others are placeholders for future decisions.

---

## ADR-001 – Strategy V1 specification as frozen reference

**Status:** Accepted  
**Date:** Documented in repository (see `docs/strategy-specification.md` revision history)

**Context:** Trend Strategy V1 requires a single authoritative spec before research validation and paper trading parity.

**Decision:** Strategy behavior, parameters, and assumptions are defined in `docs/strategy-specification.md`. Changes require explicit issue and review; agents must not silently modify parameters.

**Alternatives:** Inline code-only strategy without spec — rejected for auditability.

**Consequences:** Backtester and paper orchestrator must stay aligned with the spec; drift is a defect.

**Issues / PRs:** See strategy-specification git history.

---

## ADR-002 – Risk V1 specification as frozen reference

**Status:** Accepted  
**Date:** Documented in repository (see `docs/risk-specification.md`)

**Context:** Capital and exposure rules must be shared across backtest and paper paths.

**Decision:** Risk limits and kill-switch semantics documented in `docs/risk-specification.md`. V1 kill switch uses FREEZE (no new entries).

**Alternatives:** Per-environment ad hoc limits — rejected.

**Consequences:** Risk engine and paper control plane must match spec; increases require governance approval.

**Issues / PRs:** See risk-specification git history.

---

## ADR-003 – Paper Trading Orchestrator phased delivery (internal phases 1–9)

**Status:** Accepted  
**Date:** Phases 1–9 marked complete in `docs/paper-trading-orchestrator-v1.md`

**Context:** Need production-shaped paper system with PostgreSQL persistence, scheduler, recovery, and API before any live consideration.

**Decision:** Implement orchestrator in documented internal phases 1–9; phase 10 (audit + hardening) is a gate before unsupervised ops.

**Alternatives:** Direct live trading — rejected.

**Consequences:** Live Hyperliquid private API remains out of scope until phase 10 + roadmap P8 approval.

**Issues / PRs:** `services/paper_trading/README.md`

---

## ADR-004 – PostgreSQL as paper trading system of record

**Status:** Accepted  
**Date:** Alembic migrations `001`–`006` in repository

**Context:** Deterministic recovery, advisory locking, and audit trail require durable relational state.

**Decision:** Paper trading state lives in PostgreSQL via SQLAlchemy + Alembic. Single worker enforced with advisory lock.

**Alternatives:** In-memory or file-based state — rejected for production paper path.

**Consequences:** Tests requiring postgres marker; Railway deploy uses managed Postgres plugin.

**Issues / PRs:** `services/paper_trading/db/`

---

## ADR-005 – Railway four-service deployment for paper stack

**Status:** Accepted  
**Date:** Documented in `docs/railway-paper-trading-dashboard-v1.md`

**Context:** Need separated worker, read-only API, dashboard, and database with private networking.

**Decision:** Deploy `paper-trading-worker`, `paper-trading-api`, `paper-trading-dashboard`, and `paper-trading-postgres` on Railway. Only dashboard is public. Config-as-code under `deploy/railway/`.

**Alternatives:** Single monolith service — rejected for blast radius and credential isolation.

**Consequences:** Start commands live in `deploy/scripts/` and must not change without issue.

**Issues / PRs:** `deploy/railway/*.toml`

---

## ADR-006 – ISO weekly candles derived from daily aggregates

**Status:** Accepted  
**Date:** 2026 (commit introducing `_refresh_iso_weekly`, config excluding native `1w` subscription)

**Context:** Native exchange weekly candles may not align with ISO week boundaries required by strategy evaluation.

**Decision:** Do not subscribe to native `1w` stream; derive ISO weekly candles from daily aggregates in `services/market_data/`.

**Alternatives:** Use exchange-native weekly bars — rejected for boundary mismatch.

**Consequences:** Weekly refresh logic and tests must account for derived series; backfill behavior documented in market_data module.

**Issues / PRs:** Recent market_data commits on `cursor/railway-paper-dashboard-v1` branch lineage.

---

## ADR-007 – GitHub as project memory (governance)

**Status:** Accepted  
**Date:** 2026-07-13

**Context:** Roadmap, bugs, and research decisions were spread across chat and scattered docs without unified issue/PR discipline.

**Decision:** Adopt `ROADMAP.md`, `AGENTS.md`, GitHub issue templates, milestones P0–P9, and `scripts/github_project_setup.py`. Chat is workbench only.

**Alternatives:** Notion-only or chat-only tracking — rejected.

**Consequences:** Agents must link PRs to issues; seed issues created for P0–P2 gaps.

**Issues / PRs:** PR #29 (`chore/project-governance`), Issue #2.

---

## ADR-008 – Live / micro-live trading

**Status:** To be decided

**Context:** Roadmap P8 requires separated micro-live system.

**Decision:** *Not yet made.* Live trading remains disabled.

**Alternatives:** Paper-only indefinitely; micro-live on Hyperliquid — TBD.

**Consequences:** TBD upon human approval issue.

---

## ADR-009 – Strategy/Risk V1 parameter inventory and change control

**Status:** Accepted  
**Date:** 2026-07-13

**Context:** Strategy V1 and Risk V1 are frozen references, but parameters can drift when defaults live across docs and code. Research validity requires explicit, published parameters and controlled changes.

**Decision:** Publish a single parameter inventory in `docs/strategy-v1-parameter-inventory.md` derived from the frozen specs and the code defaults. Any parameter change (including defaults, validation maximums, or coupled execution guardrails) requires a dedicated GitHub issue and PR review; changes must update the relevant spec tables and the inventory together.

**Alternatives:** Implicit defaults in code only — rejected for auditability and reproducibility.

**Consequences:** Parameter drift becomes a governance defect. Backtests and paper runs must record the inventory version (commit hash) used.

**Related Issues / PRs:** Issue #4 (Bestehende Strategieparameter dokumentieren und einfrieren).

---

## ADR-010 – Definition of Done adoption

**Status:** Accepted  
**Date:** 2026-07-13

**Context:** `docs/DEFINITION_OF_DONE.md` existed but was not enforced in review. Governance PRs #29, #36, #43 used the PR template DoD section; formal adoption was missing.

**Decision:** Bind DoD to review via PR template, `AGENTS.md`, `docs/PROJECT_OPERATING_SYSTEM.md`, and `docs/DEFINITION_OF_DONE.md` § Review policy. Reviewers must reject PRs lacking test evidence (commands + results) unless explicitly waived in the issue.

**Alternatives:** Wait for CI automation — deferred; manual review policy adopted first.

**Consequences:** Merge without test evidence is a process defect. Optional CI comment remains future work.

**Related Issues / PRs:** Issue #5.

---

## ADR-011 – Solo-maintainer DoD enforcement (interim)

**Status:** Accepted
**Date:** 2026-07-14

**Context:** Issue #5 requires test evidence in post-governance PRs and reviewer rejection of missing test evidence. The repository currently has a single active maintainer; merged PRs #29–#57 have no formal GitHub reviews. Blocking P0 on retroactive reviews would delay governance exit without improving safety.

**Decision:** DoD is enforced in the solo-maintainer phase as follows:

1. Every PR must include the PR template **Tests** section with executed commands and results, or an explicit N/A justification tied to the issue scope.
2. The **Definition of Done** checklist in the PR body must be completed honestly before merge.
3. Governance-related paths are validated by `.github/workflows/github-governance-setup.yml` on pull requests.
4. Formal GitHub review (approve / request changes) becomes mandatory when a second maintainer is added or a reviewer is explicitly assigned on the PR.

**Baseline post-governance PRs with test evidence:** #50, #54, #57 (merged after governance rollout #29).

**DoD checklist in PR body:** first demonstrated in #57; mandatory for all merges from ADR-011 onward. PR template and docs reference DoD since #29.

**Alternatives:** Require retroactive reviews on closed PRs — rejected as performative without adding verification.

**Consequences:** Solo merges without test commands in the PR body remain a process defect. Full reviewer enforcement deferred until team growth; tracked when #52 or staffing changes.

**Related Issues / PRs:** Issue #5, PR #50, PR #54, PR #57.

---

## ADR-012 – P2 dependency decision for P3 historical data

**Status:** Accepted
**Date:** 2026-07-14

**Context:** P3 (versioned historical market data) requires an operational baseline for database backup and restore when storage ADR selects PostgreSQL. Issue #11 (backup/restore drill) has a completed local restore drill (PR #71 merged) but an outstanding Railway non-production restore.

**Decision:**

The local PostgreSQL restore drill and recovery procedures provide the operational minimum required for P3 planning and implementation.

The outstanding Railway non-production restore in Issue #11 remains mandatory for full P2 completion but does **not** block local P3 historical-data development.

P3 changes must not depend on untested Railway restore behavior.

**Alternatives:** Block all P3 work until Railway restore is proven — rejected; local drill satisfies planning and implementation risk for dataset work.

**Consequences:** #11 stays open on the P2 milestone. Epic #45 and P3 sub-issues may proceed. Any P3 storage implementation that shares PostgreSQL must document backup/restore assumptions explicitly.

**Related Issues / PRs:** Issue #11, Issue #45, PR #71, `docs/P3_HISTORICAL_DATA_PLAN.md`.

---

## ADR-013 – Immutable dataset storage (hybrid PostgreSQL + filesystem)

**Status:** Accepted
**Date:** 2026-07-14

**Context:** P3 requires append-only dataset catalog, immutable raw provider payloads, and normalized candle persistence (#79). Options: PostgreSQL only, filesystem/object store only, or hybrid. Paper trading already uses Railway PostgreSQL (ADR-004); local backup/restore drill exists (ADR-012, #71).

**Decision:** Adopt a **hybrid** storage architecture:

1. **PostgreSQL** (shared paper DB, new `market_data_*` tables only): dataset manifest catalog, normalized candle rows, quarantine/quality metadata references. Append-only by convention: no `UPDATE`/`DELETE` on published dataset rows; corrections insert new `dataset_id` with `parent_dataset_id`.
2. **Filesystem** (configurable `MARKET_DATA_DATASET_ROOT`): content-addressed raw JSON artifacts at `raw/{sha256}.json`. Immutable: write-if-not-exists; hash verified on read.
3. **Lookup:** Research and import tooling resolve `dataset_id` via PostgreSQL catalog; raw bytes loaded by `raw_content_hash` / path.

**Alternatives considered:**

| Option | Rejected because |
|--------|------------------|
| PostgreSQL only (bytea blobs) | Large raw payloads bloat DB backups and migration cost |
| Filesystem only | No transactional catalog alongside paper trading; weaker query by `dataset_id` |
| Separate database | Extra Railway service and backup scope for solo-maintainer phase |

**Backup/restore impact (R-009):**

- PostgreSQL tables included in existing `pg_dump` / restore drill scope.
- Raw files require `MARKET_DATA_DATASET_ROOT` volume backup documented in storage runbook addendum (#79).
- P3 must not depend on untested Railway restore (#11 waiver per ADR-012).

**Consequences:** Alembic migration `010` adds market-data tables only; paper-trading tables untouched. Import pipeline (#80) writes raw files before normalization.

**Related Issues / PRs:** Issue #78, Issue #79, `docs/market-data-contract.md`.

---

## ADR-014 – One Hyperliquid multi-asset platform with asset-specific profiles

**Status:** Accepted
**Date:** 2026-07-15

**Context:** The roadmap expands beyond BTC/ETH/SOL crypto perpetuals to HIP-3 equity, index, and commodity perpetuals on the same Hyperliquid ecosystem. A governance decision is needed on repository boundaries, asset modeling, and phase gates before any implementation.

**Decision:**

1. Crypto, equity, index, and commodity **perpetuals** are supported within the **same** research and paper-trading platform (single repository unless future technical or regulatory limits prove otherwise).
2. Asset-class differences are modeled via **asset metadata profiles**, provider/DEX configuration, cost/funding models, and risk profiles — not by treating all symbols identically.
3. Planned profile types: `CRYPTO_24_7`, `HIP3_EQUITY_PERP`, `HIP3_INDEX_PERP`, `HIP3_COMMODITY_PERP`.
4. Equity/index/commodity exposure is **synthetic perpetual exposure**; the system must not describe these as holding real shares or physical commodities.
5. **P7** allows research, backtest, shadow, and paper only. **P8 live trading** still requires human approval.
6. Multi-asset expansion must **not** bypass **P5** (validation) or **P6** (paper soak).
7. Architectural split into separate repositories is required only if evidenced by technical or regulatory constraints.

**Alternatives:**

| Option | Rejected because |
|--------|------------------|
| Separate repo per asset class | Duplicates research, risk, and monitoring infrastructure |
| Single undifferentiated asset model | Ignores funding, oracle, session, and corporate-action differences |

**Consequences:**

- Asset profiles become mandatory before new markets trade in paper or live paths.
- Costs and risks must be validated per profile.
- P7 milestone renamed to **Multi-Asset and Independent Strategy Candidates**.
- Planning issues for metadata contract, HIP-3 equity validation, and correlated exposure model are tracked on P7; implementation is out of scope until those gates pass.

**Related Issues / PRs:** `ROADMAP.md` § P7, `docs/ARCHITECTURE.md` § Multi-asset target architecture, P7 planning issues (governance setup).

### Amendment 2026-07-18 (ADR-018 alignment)

**Status:** Accepted amendment

1. **Research universe ≠ execution venue.** ADR-014's Hyperliquid / HIP-3
   focus describes the *first execution and paper venue path*, not the limit of
   research universes. Research MAY study Crypto, Forex, Equity Indices,
   Commodities, Rates, and Equities while execution remains Hyperliquid /
   existing paper only.

2. **Orthogonal metadata axes** (single registry via #104 — no second registry):
   - `asset_class`: `CRYPTO` | `FX` | `EQUITY` | `INDEX` | `COMMODITY` | `RATES`
   - `instrument_type`: `SPOT` | `PERPETUAL` | `FUTURE` | `CASH_EQUITY` | `SYNTHETIC_PERPETUAL`
   - `venue` / execution profile (e.g. Hyperliquid core, HIP-3 market)

   Example combinations: `CRYPTO+PERPETUAL`, `EQUITY+SYNTHETIC_PERPETUAL`,
   `INDEX+SYNTHETIC_PERPETUAL`, `COMMODITY+FUTURE`, `COMMODITY+SYNTHETIC_PERPETUAL`,
   `FX+SPOT`, `RATES+FUTURE`.

   HIP-3 index and commodity markets are **synthetic perpetuals**, not futures.
   Legacy names `CRYPTO_24_7`, `HIP3_EQUITY_PERP`, `HIP3_INDEX_PERP`,
   `HIP3_COMMODITY_PERP` map into this registry as venue-specific aliases.

3. **Identity scaffolding exception:** InstrumentId and additive plumbing
   (#128–#130) are cross-cutting architectural scaffolding, **not** P7 runtime
   activation. Merge before P5/P6 is allowed only under ADR-018 parity and
   freeze-window rules. Points 5–6 of the original decision (P7
   research/shadow/paper only; must not bypass P5/P6 for *multi-asset
   activation*) remain in force. Scaffolding ≠ activation.

**Related:** ADR-018, #104, #128–#130.

---

## ADR-015 – Retire Codex review gate

**Status:** Accepted

**Date:** 2026-07-17

**Context:** The read-only Codex review gate (Issue #149, `.agent-loop/`) blocked productive Windows workflows (OS isolation fail-closed), added high operational cost, and did not improve merge safety enough to justify keeping it.

**Decision:** Remove the Codex review gate and all mandatory Codex-approval requirements. Quality gate is: implement → tests → CI → human merge. Agents must not auto-merge or auto-deploy.

**Alternatives:** Keep gate with WSL/CI-only APPROVED — rejected as too costly relative to value.

**Consequences:**

- `.agent-loop/`, `tests/agent_loop/`, and `00-mandatory-codex-review.mdc` are removed.
- CI path classifier no longer has an `agent_loop` slice.
- Label `agent:codex-review` is no longer seeded by governance setup.
- Issue #149 is closed as superseded by this retirement.

**Related Issues / PRs:** #149; PR for `chore/remove-codex-review-gate`.

---

## ADR-016 – Enforce main required checks via repository rulesets

**Status:** Accepted

**Date:** 2026-07-17

**Context:** Classic branch protection API returns HTTP 403 on this private
repository without GitHub Pro (#65). A repository ruleset on `main` already
blocked deletion/force-push and required PRs, but did not require CI checks.

**Decision:** Complete #65 by adding the Phase-1 required status check contexts
(`validate`, `requirements-baseline`, `lint`, `test`, `test-market-data`,
`test-deploy`, `postgres`) to ruleset `main` (id 19091297) with strict policy.
Do not claim classic branch protection is enabled.

**Alternatives:** Upgrade to GitHub Pro for classic protection; make the repo
public — rejected as unnecessary once rulesets enforce the same checks.

**Consequences:** Docs (`docs/branch-protection.md`, `docs/baseline-paper-v1.md`)
describe rulesets as the source of truth. Phase 2 may retarget check names per
`docs/ci/REQUIRED_CHECK_MIGRATION.md`.

**Related Issues / PRs:** #65

---

## ADR-017 – P5 execution uses forward holdout and private research store

**Status:** Accepted (process)
**Date:** 2026-07-17

**Context:** P5 planning established that historical BTC/ETH/SOL periods cannot be proven untouched OOS. Economic results must not enter the public tree.

**Decision:**

1. Final OOS uses a **forward holdout** starting at human Candidate Freeze UTC (#197).
2. Private Specs/results/decisions live in `Pain1234/save-money-trading-bot-private-research` (#181).
3. Numeric ACCEPT/REJECT/INCONCLUSIVE gates are **proposed** in public docs and become binding only after human freeze comments on #198.
4. Feature warmup (monthly EMA 20 ≈ 20 monthly bars) is separate from purge/label embargo; see exposure audit.
5. One-shot OOS (#204) and final decision (#205) remain blocked until freezes, private robustness packs, and sample-sufficiency are met.

**Alternatives:** Relabel historical windows as untouched OOS — rejected (leakage / honesty risk).

**Consequences:** P5 may conclude `INCONCLUSIVE` if the forward window is too short; that is not a promotion. Public PRs carry methodology/framework only.

**Related Issues / PRs:** #47, #181, #196–#205

---

## ADR-018 – Centralized intent allocation and a single execution owner

**Status:** Accepted (architecture / planning — **not** a runtime activation)
**Date:** 2026-07-18

**Ownership:** ADR-018 is the **sole** architecture decision record for
centralized Strategy Intent allocation and the single execution owner per
trading account. Other ADRs (including ADR-014) may reference this model; they
MUST NOT redefine, renumber, or claim a competing intent-allocation or
multi-writer execution-owner design.

**Context:**
The long-term target is a multi-universe, multi-asset, multi-timeframe,
multi-strategy research platform with optional later execution. Today strategies
emit `SignalIntent` / `TradeIntent` on a single paper path. Uncoordinated bots
writing orders to the same account would break accounting, risk, and
reconciliation (R-025). Hyperliquid subaccounts are a later optional isolation
tool (P8), not a P7 runtime goal.

This ADR records an **architecture decision**. It does **not** authorize
multi-asset runtime, multi-strategy live/paper execution, new markets,
subaccounts, or new venue adapters.

**Decision:**

1. Multiple strategies MAY emit research and shadow signals concurrently.
2. Strategies MUST NOT independently submit, amend, or cancel orders on the
   same trading account.
3. Each strategy emits a normalized **Strategy Intent** (portfolio-level
   contract; distinct from today's single-path `SignalIntent` / `TradeIntent`).
   Strategy-produced strength fields use names such as `signal_strength` or
   `strategy_conviction` (or `model_score`). These are **not** validation
   confidence, evidence confidence, or permission to trade. Evidence confidence
   remains a research-only artifact (P4.9 scorecard).
4. A central **Portfolio Allocator** decides eligibility, relative
   attractiveness, risk-cluster membership, and risk-budget assignment, and
   emits **sleeve-level desired targets** (per strategy/sleeve × instrument).
   It does **not** emit the final account-level net position.
5. A **Global Risk Engine** evaluates the combined sleeve portfolio (may scale
   or clip sleeve targets under portfolio limits).
6. A separate **Target Position Netting** step collapses sleeve targets into
   exactly one **account-level net target position per instrument** for the
   Execution Owner. Netting is not folded into the Allocator.
7. Exactly one **Execution Owner** may create, amend, or cancel orders for a
   given trading account.
8. Venue adapters (Hyperliquid now; others later) sit after the Execution
   Owner. Strategies MUST NOT depend on venue-specific symbols, funding
   fields, or order objects.
9. **Research universe ≠ execution venue** (see ADR-014 amendment).

**Allocator vs netting (binding boundary):**

| Stage | Output |
|-------|--------|
| Portfolio Allocator | Sleeve-level desired targets (strategy/sleeve × instrument) plus eligibility / ranking / cluster / budget decisions |
| Global Risk Engine | Risk-adjusted sleeve targets (scale/clip); still sleeve-scoped |
| Target Position Netting | Single account-level **net** target position per instrument |

Do not describe the Allocator as emitting the final net instrument position;
that is exclusively the netting stage before the Single Execution Owner.

**Target pipeline:**

```text
Strategy Modules
      │
      ▼
Strategy Intents
      │
      ▼
Eligibility Gates
      │
      ▼
Opportunity Ranking
      │
      ▼
Correlation Clustering
      │
      ▼
Portfolio Allocator
      │
      ▼
Global Risk Engine
      │
      ▼
Target Position Netting
      │
      ▼
Single Execution Owner
      │
      ▼
Venue Adapter
```

Full research-facing chain:

```text
Market Data → Universe Discovery → Asset Profile → Multi-Timeframe Context
→ Strategy Signals → Normalized Strategy Intents → Eligibility Gates
→ Opportunity Ranking → Correlation Clustering → Portfolio Allocation
→ Global Risk Engine → Target Position Netting → Single Execution Owner
→ Venue Adapter → Hyperliquid or later venues
```

**Identity scaffolding exception (cross-cutting, not P7 runtime):**

- Issues #128–#130 (InstrumentId + additive plumbing) MAY merge before P5/P6
  complete, only as identity scaffolding.
- Existing BTC/ETH/SOL candles, signals, trade decisions, position sizes,
  orders, fills, fees and PnL MUST remain **semantically and economically
  equivalent** under canonical golden fixtures. Additive identity metadata and
  serialization-only differences are permitted when explicitly documented and
  excluded from the economic parity comparison. Numeric parity uses clear
  tolerances or canonical snapshots defined in the issue/PR.
- Any economic change to candles, signals, trade decisions, position sizes,
  orders, fills, fees, or PnL blocks the merge.
- Does **not** activate new markets, strategies, asset-profile runtime,
  ranking, clustering, allocation, multi-strategy execution, subaccounts, or
  new venue adapters.
- Each of #128, #129, #130 uses its own clean branch and PR.
- Do not use or modify branch `fix/research-symbol-constraints` for this work.
- **Before the P5 candidate freeze and any actual P5 execution**, #128–#130
  must either (1) be merged and pass all parity gates, or (2) be explicitly
  deferred until after P6. No identity migration may occur between candidate
  freeze and completion of the corresponding validation and soak sequence
  without creating a new candidate version and a new documented freeze.

**Phase gates:**

- P7 may define contracts, ADRs, and planning issues.
- Productive multi-asset / multi-strategy activation remains blocked on P4
  completion, P5 honest validation, P6 paper soak, and required human
  approvals.
- Subaccount / multi-process live execution is P8 planning only (#184); not
  implemented under P7.

**Alternatives rejected:**

| Option | Rejected because |
|--------|------------------|
| Independent bots per strategy on one account | Uncoordinated orders; broken risk/reconcile (R-025) |
| Subaccounts as first isolation for P7 | Premature; belongs to P8; optional later |
| Strategies emit venue orders directly | Couples research to Hyperliquid; blocks multi-venue |

**Consequences:**

- Extend planning issues #104, #106, #135, #139; keep #128–#130 as scaffolding.
- Planning issues for Multi-Timeframe Role Contract (#304) and Normalized Portfolio
  StrategyIntent Contract (#305).
- R-025 added to the risk register.
- No runtime multi-strategy allocator is authorized by accepting this ADR.

**Related Issues / PRs:** ADR-014 (amended), #104, #106, #128–#130, #135, #139,
#183, #184, #304, #305; `ROADMAP.md` § P7/P8; `docs/ARCHITECTURE.md` § Multi-asset target
architecture.

---

## ADR-019 – Regime-based Strategy Evidence Scorecard as layered P4 extension

**Status:** Accepted (architecture / governance)
**Date:** 2026-07-18

**Context:** P4 already provides ExperimentRegistry, robustness orchestration (#247),
versioned gate evaluation (#248), and validation studies (#249). Reviewers still need
a **structured evidence profile** that answers integrity, critical gates, per-regime
quality, confidence, behaviour, parameter-area stability, and transition risk
**separately** — without a second registry or auto-promotion. Collapsing those into
one compensating score would recreate overfitting and UI greenwashing risks (R-003).

**Decision:**

1. Introduce Epic **P4.9 – Regime-Based Strategy Evidence Scorecard** (#295) inside
   the existing P4 milestone (no new main milestone).
2. Bind the scorecard to the fixed layer model in
   [`docs/research/REGIME_SCORECARD.md`](research/REGIME_SCORECARD.md): Integrity →
   Critical Gates → Regime Quality → Evidence Confidence → Behaviour → Global Profile.
3. Extend existing components only; forbid a second scorecard DB, second gate service,
   separate results register, or automatic paper/live promotion.
4. Generic P4 gate/scorecard policy must not hard-code private Strategy V1 thresholds;
   P5 binding/freeze is [#294](https://github.com/Pain1234/save-money-trading-bot/issues/294)
   after infrastructure lands, anchored on [#198](https://github.com/Pain1234/save-money-trading-bot/issues/198) /
   [#199](https://github.com/Pain1234/save-money-trading-bot/issues/199).
5. Missing metrics are `NOT_AVAILABLE` / `INCONCLUSIVE`, never silently `0`. A weighted
   aggregate score, if any, is sort-aid only and cannot override integrity FAIL or
   critical gate FAIL.

**Alternatives:**

- Monolithic total score for accept/reject — rejected (compensates failures; overfitting magnet).
- Parallel scorecard microservice/registry — rejected (duplicates SoT; audit drift).
- Defer all regime evidence to private P5 notes only — rejected (framework must be
  reusable for later strategies under P4).

**Consequences:** Implementation follows dependency chain #284→#285→#286→{#287–#290}→#291→#292→#293→#294.
UI must surface integrity/gate failures and main weakness prominently. Private economic
results stay out of the public repo (#181).

**Related Issues / PRs:** #295, #284–#294, #247–#250, #198, #199, #181

---

## ADR-020 – Strategy V1 validation binds frozen P4.9 scorecard policy versions

**Status:** Accepted (governance; Human Freeze sign-off **pending** on #294)
**Date:** 2026-07-19

**Context:** P4.9 delivered versioned, content-hashed scorecard / classifier /
confidence / behaviour (and related) policies on `main`. Strategy V1 honest
validation (#198/#199 protocol) must not silently drift when those policies are
edited under the same version string, and must not treat the final holdout as
an optimization target. Epic ADR-019 deferred Strategy-specific binding to #294.

**Decision:**

1. Bind Strategy V1 validation evidence assembly to the pinned versions and
   content hashes in
   [`docs/research/p5/P5_SCORECARD_POLICY_BIND.md`](research/p5/P5_SCORECARD_POLICY_BIND.md)
   against freeze `main` SHA `5cb3a7bf2b310b15f932ccf24e934025990ebf6d`.
2. Primary pins: scorecard policy `1.0`, confidence `1.0`, behaviour `1.0`,
   regime classifier `1.0` (transitions included), gate policy `1.1` when gates
   are bound. Quality-score and parameter-area policies `1.0` are documented
   companions (not standalone ACCEPT gates).
3. Extend #198/#199; do **not** replace their proposed numeric ACCEPT/REJECT
   rules. Those remain human-frozen on their own issues.
4. **Holdout C stays closed.** #204 / #205 remain blocked. No automatic
   `ACCEPT_FOR_P6` from scorecard PASS / high quality / confidence.
5. Silent same-version policy mutation fails closed via content hash. New
   thresholds or taxonomy require a new version + dedicated issue/PR.
6. Human sign-off on #294 (`SCORECARD POLICY BIND FROZEN`) is required before
   treating this bind as execution-ready; until then status is
   `PENDING_HUMAN_SIGN_OFF`.

**Alternatives:**

- Leave P4.9 policies unbound for P5 — rejected (drift / post-hoc retune risk).
- Open holdout when documenting the bind — rejected (violates one-shot OOS).
- Encode private Strategy V1 economic thresholds into public scorecard policy —
  rejected (ADR-019 / #181).

**Consequences:** Private robustness packs (#251–#254) and one-shot OOS (#204)
must cite these pins. UI/scorecard surfaces remain non-promotional. Candidate
freeze (#196), partitions (#197), and #198/#199 human locks remain separate
gates.

**Related Issues / PRs:** #294, #295, #198, #199, #181, #204, #205, ADR-019

---

## Template for new entries

```text
ADR-NNN – Title
Status: Proposed / Accepted / Superseded / Rejected
Date:
Context:
Decision:
Alternatives:
Consequences:
Related Issues / PRs:
```

Add new ADRs at the bottom; supersede old ADRs rather than deleting.
