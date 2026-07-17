# P4 acceptance checklist

Checkboxes reflect **merged** PRs that close the listed issues. Untick if an issue is reopened.

| Criterion | Issue | Evidence |
|-----------|-------|----------|
| ExperimentSpec versioned + validatable | #141 | PR #150 |
| Identity: `experiment_id` / `run_id` / `attempt_id` + immutable RunManifest | #142 | PR #154 |
| Strategy interface/resolver documented + pinned | #148 | PR #161 |
| Metrics + benchmark compute (`buy_and_hold_*`) | #144 | PR #157 |
| Cost versions + funding rate applied (no P5 stress) | #49 | PR #158 |
| Research runner + atomic artifacts | #143 | PR #155 (runner) |
| Registry reconstruct / checksum / compare / invalidation | #145 | PR #159 |
| Backtester/paper **signal** parity + intentional differences | #48 | PR #156 |
| CI `research-repro` double-run semantic gate | #146 | PR #160 |
| Dataset binding to P3 DatasetManifest + quarantine | #163 | PR #173 |
| Funding semantics + gross/net includes funding; metrics/cost `1.1` | #164 | PR #169 |
| Registry checksum trust anchor | #165 | PR #170 |
| Inject resolved StrategyEngine into BacktestEngine | #166 | PR #172 |
| Registry compare: full `semantic_spec_dict` + RunManifest | #167 | PR #171 |
| Documentation complete (this folder) | #147 | PR (this docs PR) |
| No new markets / live trading / P5 gates pre-empted | — | scope review |

Milestone DoD (from #147):

- [x] ExperimentSpec versioned and validatable (#141)
- [x] Dataset manifest from P3 mandatory (#163)
- [x] Strategy interface/resolver contract present and pinned (#148 / #166)
- [x] Strategy version and git commit pinned
- [x] Benchmark definitions (`benchmark_id`/`version`, parity) present (#144)
- [x] Deterministic `experiment_id` (semantic spec fields only; owner/notes excluded) (#142)
- [x] Deterministic `run_id` + separate `attempt_id` (#142)
- [x] Immutable RunManifest
- [x] Reproducible research runner (#143)
- [x] Atomic and verifiable artifacts (#165 trust anchor)
- [x] Versioned metrics schema (#144 / #164 → `1.1`)
- [x] Mandatory fee/slippage/funding assumptions (#49) — **without** P5 cost-stress gates
- [x] Gross and net results separated (#164)
- [x] Backtester/paper parity proven (#48)
- [x] Golden-master / signal parity regression protection present
- [x] Experiment registry present (#145)
- [x] Invalidation via registry/sidecar only; RunManifest unchanged
- [x] CI reproducibility gate green (#146)
- [x] Semantic registry compare (#167)
- [x] Documentation complete (#147)
- [x] No new markets activated
- [x] No strategy parameters changed as a P4 deliverable
- [x] No live-trading code added
- [x] P5 gates not pre-empted (no OOS/walk-forward/cost-stress as P4 acceptance)

Public-release gates (#176–#180) are tracked on the same GitHub milestone but are **not** research-engine ACs; they close after this docs issue.

See `ROADMAP.md` P4 section and [README.md](README.md).
