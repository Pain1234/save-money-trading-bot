# P5 Phase A – Bestandsaudit (evidence-based)

**Audit date:** 2026-07-17 (planning); **resync:** 2026-07-17 against `main` tip `92b3e4a` (post #206–#210 / #65)
**Audited `main` HEAD at planning branch creation:** `e804be5` (merge of docs/p4-milestone-close #194)
**Rule:** No assumptions recorded as facts. `UNKNOWN` where evidence is missing.

## Audit table

| Bereich | aktueller Stand | Evidenz | P5-Auswirkung | offene Entscheidung |
|---------|-----------------|---------|----------------|---------------------|
| `main` branch | P4 complete; P4-fix #206–#210 closed; metrics schema **1.2** on `main` | `git log` / ROADMAP; `METRICS_SCHEMA_VERSION=1.2` | Freeze/protocol must pin **1.2**, not 1.1 | Keep docs synced at Candidate Freeze SHA |
| P4 milestone (GitHub) | **No** GitHub milestone titled `P4 – Research Engine` in API list (IDs jump P3→P5) | `gh api .../milestones` 2026-07-17 | Track P4 completion via docs/issues, not milestone object | Whether to recreate P4 milestone for archive (out of P5 scope) |
| P4 research engine | Complete on `main` | `docs/research/P4_ACCEPTANCE.md`; closed #141–#147, #148, #49, #48, #163–#167; ROADMAP P4 **Complete** | Entry-gate research prerequisites largely met | Re-run green regression suite before first P5 execution (P5-00) |
| P4 public-release gates | Closed | #176–#180 closed; PR #189–#194 | Boundary docs exist; does not replace #181 P5 artifact path | Private storage path for P5 results (#181) |
| P4 correction issues | **CLOSED / merged:** #206, #207, #208, #210 | GitHub issue state + `main` metrics/benchmark contracts | No longer blocks P5-00 on open P4-fix | None (resync complete) |
| P5 milestone | Exists; planning issues #196–#205 plus #47/#181 | Milestone #6 | Use existing milestone only | None for numbering |
| Issue #65 | Ruleset required checks on `main`; ADR-016 | Ruleset `main` id 19091297; ADR-016 | Governance gate for merges; not a research blocker | None |
| Issue #47 | OPEN; R-003 OOS overfitting | Issue body + comment linking #181 | Canonical risk/overfitting checklist | Keep open until final P5 decision |
| Issue #181 | OPEN; public/private separation | Issue body + PR #222 | Must complete before first real P5 result | Merge private store + CI leak rules |
| `ROADMAP.md` P5 | Honest-validation planning present | ROADMAP P5 section | Align execution with protocol docs | Human freezes before OOS |
| Strategy V1 identity | Spec freeze 1.0 / code `1.0.0` | `docs/strategy-specification.md`; inventory | Candidate freeze can pin known defaults | Formal freeze manifest + human sign-off (P5-00) |
| Risk V1 coupling | Frozen maxima documented | `docs/risk-specification.md`; inventory | Include in freeze | Confirm risk params in freeze |
| ExperimentSpec | Versioned schema present | `docs/research/EXPERIMENT_SPEC.md`; examples | Required for runs | Real private Spec path (#181) |
| RunManifest | Immutable contract present | `docs/research/IDENTITY.md` / runner docs | Required | None for planning |
| DatasetManifest | P3 binding present | #163; `docs/P3_DATASET_REPRODUCIBILITY_AUDIT.md` | Required; production dataset IDs not in public tree | Which published dataset(s) for P5 |
| Strategy resolver | Injected into BacktestEngine | #148/#166; `docs/research/STRATEGY_INTERFACE.md` | Entry gate item | Verify on execution branch |
| Cost / slippage / funding | Semantics documented; stress is P5 | `docs/research/FUNDING.md`; **METRICS 1.2**; #49/#164/#208 | Base models usable; BH net under Spec costs | Stress multipliers (human) |
| Registry trust anchor | Present | #165 | Entry gate item | None |
| Compare semantics | Spec + RunManifest identity | #167 | Entry gate item | None |
| Backtester/paper parity | Documented signal parity | `docs/research/BACKTESTER_PAPER_PARITY.md`; #48 | Entry gate item | Decay measurement is P6/#46, not P5 |
| Bootstrap / Monte Carlo | **Not on `main` until #203 merges** | Issue #203; helper lands with that PR only | Plan methods in P5-07; do not claim present at #196 | Seed / block / n_sim freeze after #203 |
| Formal Strategy V1 OOS report | **None found** in repo | No P5 OOS artifacts | Cannot claim prior OOS pass/fail | None |
| Committed production history | **Not** in public tree | No `data/**` candle dumps; fixtures only | Holdout must bind real DatasetManifest at execution | Import/publish dataset privately |
| Example ExperimentSpec window | Example only: 2024-01-01→2024-12-31 | `examples/research/btc_eth_sol_experiment.example.json` | **Not** a locked partition; example hashes | Do not treat example year as OOS |
| Fixture dataset window | 2024-01-01→2024-01-07 synthetic | `tests/market_data/fixtures/example_dataset_manifest.json` | Test-only; not FINAL_HOLDOUT | None |
| Spec backtest variant note | Spec lists `volume_ratio_min` baseline 1.00 and backtest variant 1.20 | `docs/strategy-specification.md` Freeze table | Variant ≠ frozen candidate; freeze must pick one | Confirm freeze uses 1.00 (baseline) |
| Paper trading live candles | Ops stack may observe live BTC/ETH/SOL | Paper docs / Railway | Live paper observation ≠ research OOS, but may contaminate “untouched” claims for overlapping calendar periods | Classify ops-seen periods in exposure audit |
| Prior chats/PRs with economic results | **UNKNOWN** completeness | No exhaustive chat archive in GitHub memory | Treat undocumented viewing as UNKNOWN_EXPOSURE | Human disclosure of any viewed performance windows |
| Seeds | Example `random_seed: 42`; protocol default `42` | Example JSON; protocol | Freeze seed before OOS | Protocol seed (human) |
| Public/private boundary | Documented | `docs/governance/PUBLIC_PRIVATE_BOUNDARY.md` | Framework public; results private | Paths for private artifacts (#181) |
| Final OOS dataset | **Not opened** for formal P5 | No P5 OOS artifacts | Required condition for later P5-08 | Partition lock after exposure audit |

## P4 entry-gate checklist (planning assessment)

| Prerequisite | Planning assessment | Evidence |
|--------------|---------------------|----------|
| P4 complete on current `main` | **Met** (docs + closed P4-fix) | ROADMAP; P4_ACCEPTANCE; #194; #206–#210 closed |
| P4 regression tests green | **Must be re-verified at Candidate Freeze** | Evidenced in P5-00 |
| ExperimentSpec versioned | Met (contract) | #141 |
| RunManifest immutable | Met (contract) | #142 |
| DatasetManifest bound to inputs | Met (contract) | #163 |
| Strategy resolver executes resolved strategy | Met (contract) | #166 |
| Cost/slippage/funding semantics clear | Met (docs); metrics **1.2** | FUNDING.md; #164; #208 |
| Registry checksum trust anchor | Met (contract) | #165 |
| Compare checks Spec+Run identity | Met (contract) | #167 |
| Backtester/paper parity documented | Met | BACKTESTER_PAPER_PARITY.md |
| Strategy V1 uniquely versioned | Met at `1.0.0` | inventory / spec |
| Parameters frozen for candidate under test | Spec freeze exists; **P5 Candidate Freeze Manifest not yet signed** | P5_CANDIDATE_FREEZE.md |
| No open critical P4 defect falsifying P5 | **Met** — #206/#207/#208/#210 closed on `main` | Issue state 2026-07-17 resync |
| Public/private storage defined | Boundary docs yes; **#181 merge pending** | PUBLIC_PRIVATE_BOUNDARY; PR #222 |
| Final OOS not opened | Met | No P5 OOS artifacts |

**Conclusion:** P4-fix blockers from the planning-day audit are **cleared on `main`**. P5 may proceed with **methodology execution docs + helpers**, but Candidate Freeze, partition/protocol freezes, private store (#181), and holdout open remain human-gated. Do not open #204 until those gates pass.

## Symbols in scope

BTC, ETH, SOL only. No new assets, HYPE, or HIP-3 in P5.
