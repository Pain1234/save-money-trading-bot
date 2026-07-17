# P5 Public Core / Private Edge artifacts

**Status:** ACTIVE (Wave 0 / #181)
**Canonical issue:** [#181](https://github.com/Pain1234/save-money-trading-bot/issues/181)
**Boundary docs:** [PUBLIC_PRIVATE_BOUNDARY.md](../../governance/PUBLIC_PRIVATE_BOUNDARY.md), [PRIVATE_EDGE_EXTENSION.md](../../governance/PRIVATE_EDGE_EXTENSION.md)

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
| Generic accept/reject **process** logic | decision rule **structure** without real result numbers |
| Bootstrap / walk-forward **infrastructure** | public helpers under `services/research/` |
| Deliberately released demo results | synthetic only |

## Private (must not land in public tree)

| Type | Examples |
|------|----------|
| Frozen candidate spec with exclusive edge | private ExperimentSpec copy |
| Final parameters / rankings | beyond already-public Freeze 1.0 inventory if private deltas exist |
| Sensitive dataset partitions | real holdout calendars if treated confidential |
| Real OOS / walk-forward / stress / sensitivity / MC results | all economic tables |
| Promotion / rejection decision rationale with numbers | private decision packet |
| Confidential reports | PDF/MD with metrics |
| Next strategy change plans with edge | private notes |

## Private storage (defined)

**Private repository:** `Pain1234/save-money-trading-bot-private-research` (private visibility).

| Concern | Location | Status |
|---------|----------|--------|
| Private ExperimentSpecs | `specs/` in private repo | DEFINED |
| Private run artifacts | `artifacts/research/` in private repo | DEFINED |
| Dataset partition locks (if sensitive) | `partitions/` in private repo | DEFINED |
| Private decision packet | `decisions/` in private repo | DEFINED |
| Confidential reports | `reports/` in private repo | DEFINED |
| Public-core pin log | `PINNED_PUBLIC_CORE.txt` in private repo | DEFINED |
| Access control | GitHub private repo ACL (org/owner only) | DEFINED |

**Dependency direction:** private repo pins public `Pain1234/save-money-trading-bot` by commit SHA or release tag. Public core never depends on the private repo. Public CI never checks out private.

**Local mirror (optional):** developers may clone the private repo beside the public tree. Do not add it as a submodule. Suggested local ignore name: `../save-money-trading-bot-private-research/` (outside this clone).

## Forbidden paths / globs in the **public** repo

Do **not** commit or upload:

| Glob / path | Reason |
|-------------|--------|
| `artifacts/research/**` with real run outputs | private results |
| `**/private_experiment_spec*` | private Specs |
| `**/private_research_result*` | private results |
| `**/decisions/*ACCEPT*` / `*REJECT*` / `*INCONCLUSIVE*` with metrics | private decisions |
| `**/*oos*result*` / `**/*walk_forward*result*` containing numbers | private validation |
| Screenshots of dashboards/metrics in `docs/` or issue attachments | leakage |

Synthetic fixtures under `tests/` and `examples/research/` remain allowed.

## CI / PR leakage protection

- [x] Forbidden paths/globs documented (this section)
- [x] PR template reminder: no private P5 numbers
- [x] Public Actions must not upload private research artifacts (no workflow may check out `save-money-trading-bot-private-research`)
- [x] Screenshots: redact or keep offline / private repo only
- [x] Issue comments on #47 / #181 / P5 issues: **process and checklists only**; link to private paths without pasting tables

### PR author checklist (binding)

Before opening a PR that touches research/P5:

1. Confirm the diff contains **no** real PnL, drawdown, trade lists, or holdout calendars.
2. Confirm no private Spec JSON/YAML with production dataset hashes intended to stay confidential.
3. Confirm CI will not gain a new `actions/checkout` of the private research repo.

## Linkage to P5 issues with private results

| Issue | Public tracks | Private stores |
|-------|---------------|----------------|
| #200 Walk-forward | status checklist | fold metrics / aggregates |
| #201 Cost stress | status checklist | stress tables |
| #202 Parameter stability | status checklist | sensitivity surface |
| #203 Bootstrap / MC | status checklist | distributions / quantiles |
| #204 Final OOS | status checklist | one-shot OOS artifacts |
| #205 Final decision | outcome code only (optional) | full decision packet with numbers |

Public issues track **status and checklists only**.
