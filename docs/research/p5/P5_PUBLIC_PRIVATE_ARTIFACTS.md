# P5 Public Core / Private Edge artifacts

**Status:** PLANNING  
**Canonical issue:** [#181](https://github.com/Pain1234/save-money-trading-bot/issues/181)  
**Boundary doc:** `docs/governance/PUBLIC_PRIVATE_BOUNDARY.md`

## Gate

**#181 must be complete before the first real P5 economic result is produced or published.**

P5 must never write private results to:

- public GitHub issues / PR comments
- public Actions logs or artifacts
- public repository paths under tracked `artifacts/` or docs with real metrics
- publicly visible screenshots

## Public (allowed in this repo)

| Type | Examples |
|------|----------|
| Validation framework | research runner, schemas, registry code |
| Methodology | this `docs/research/p5/*` planning set |
| Empty templates | freeze/protocol/decision templates |
| Synthetic examples | `examples/research/*`, fixtures |
| Generic metric definitions | `METRICS_DEFINITIONS.md` |
| Generic accept/reject **process** logic | decision rule **structure** without real thresholds tied to secret results |
| Bootstrap / walk-forward **infrastructure** | once implemented as framework |
| Deliberately released demo results | synthetic only |

## Private (must not land in public tree)

| Type | Examples |
|------|----------|
| Frozen candidate spec with exclusive edge | private ExperimentSpec copy |
| Final parameters / rankings | beyond already-public Freeze 1.0 inventory if further private deltas exist |
| Sensitive dataset partitions | real holdout calendars if treated confidential |
| Real OOS / walk-forward / stress / sensitivity / MC results | all economic tables |
| Promotion / rejection decision rationale with numbers | private decision packet |
| Confidential reports | PDF/MD with metrics |
| Next strategy change plans with edge | private notes |
| Asset/portfolio decisions beyond public BTC/ETH/SOL scope | n/a for P5 (no new assets) |

## Planned private storage (fill in #181)

| Concern | Planned location | Status |
|---------|------------------|--------|
| Private ExperimentSpecs | TBD (private repo / encrypted store / out-of-tree) | OPEN |
| Private run artifacts | TBD | OPEN |
| Private decision packet | TBD | OPEN |
| Access control | TBD | OPEN |

CI must not require private repo access for public workflows.

## CI / PR leakage protection (plan)

- [ ] Document forbidden paths/globs for real metrics
- [ ] PR template reminder: no private P5 numbers
- [ ] Actions: no upload of private research artifacts on public workflows
- [ ] Screenshots: redact or keep offline
- [ ] Issue comments on #47/#181: process only; link to private store without pasting tables

## Linkage

All P5 issues that produce economic output (P5-04…P5-09, and diagnostics) inherit this classification. Public issues track **status and checklists only**.
