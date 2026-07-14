# GitHub Project setup — P2.5 and P7 issues

Manual GitHub Project v2 field values for issues created by `scripts/github_project_setup.py` when automation cannot set project fields.

**Project name:** `Trading System Roadmap`

See also `docs/PROJECT_OPERATING_SYSTEM.md` § GitHub Project (v2).

---

## Required custom fields

| Field | Type | Values |
|-------|------|--------|
| Phase | Single select | P0, P1, P2, **P2.5**, P3–P9 |
| Workstream | Single select | **Platform**, **Operations**, **Research**, **Risk** |
| Status | Single select | Backlog, Ready, In Progress, Review, Blocked, Done |
| Priority | Single select | P0, P1, P2, P3 |

---

## P2.5 issues — recommended project fields

| Seed key | Title | Phase | Workstream | Status | Priority |
|----------|-------|-------|------------|--------|----------|
| `p25-perf-establish-dashboard-api-performance-baseline` | perf: establish dashboard and API performance baseline | P2.5 | Platform | Ready | P1 High |
| `p25-perf-add-request-timing-database-query-instrumentation` | perf: add request timing and database query instrumentation | P2.5 | Platform | Backlog | P1 High |
| `p25-perf-audit-dashboard-sql-queries-database-indexes` | perf: audit dashboard SQL queries and database indexes | P2.5 | Platform | Backlog | P1 High |
| `p25-perf-remove-redundant-status-readiness-database-reads` | perf: remove redundant status and readiness database reads | P2.5 | Platform | Backlog | P2 Medium |
| `p25-feat-add-dashboard-summary-api-endpoint` | feat: add dashboard summary API endpoint | P2.5 | Platform | Backlog | P2 Medium |
| `p25-perf-define-implement-dashboard-cache-policy` | perf: define and implement dashboard cache policy | P2.5 | Platform | Backlog | P2 Medium |
| `p25-ux-add-loading-states-streaming-dashboard-routes` | ux: add loading states and streaming to dashboard routes | P2.5 | Platform | Backlog | P2 Medium |
| `p25-test-add-dashboard-performance-regression-checks` | test: add dashboard performance regression checks | P2.5 | Platform | Backlog | P2 Medium |
| `p25-ops-complete-production-dashboard-acceptance` | ops: complete production dashboard acceptance | P2.5 | Operations | Backlog | P1 High |

**Recommended sequencing:** baseline → instrumentation → SQL audit → redundant reads → summary API → cache → loading states → regression tests → production acceptance.

Do not set all P2.5 issues to **Ready** simultaneously (WIP limit: one large issue in progress).

---

## P7 issues — recommended project fields

| Seed key | Title | Phase | Workstream | Status | Priority |
|----------|-------|-------|------------|--------|----------|
| `p7-research-define-hyperliquid-multi-asset-market-metadata-contract` | research: define Hyperliquid multi-asset market metadata contract | P7 | Research | Backlog | P3 Low |
| `p7-research-define-hip3-equity-perpetual-validation-requirements` | research: define HIP-3 equity perpetual validation requirements | P7 | Research | Backlog | P3 Low |
| `p7-risk-define-correlated-multi-asset-exposure-model` | risk: define correlated multi-asset exposure model | P7 | Risk | Backlog | P3 Low |

P7 issues are **planning only** until P5 validation and P6 paper soak complete (ADR-014).

---

## Linking issues to the project

1. Run `python scripts/github_project_setup.py --apply --skip-project` to create milestones and seed issues.
2. In GitHub: **Projects → Trading System Roadmap → Add item** — search by seed key marker or title.
3. Set Phase, Workstream, Status, and Priority per tables above.
4. Update `docs/RISK_REGISTER.md` issue links (R-019–R-024) when issue numbers are known.
