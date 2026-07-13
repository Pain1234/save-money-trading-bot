# Project Operating System

How this trading research and operations repository is run day to day.

**Principle:** Chat is the workbench. **GitHub is the project memory.**

Cursor/Codex chats must not be the only record of decisions, bugs, or experiment outcomes.

---

## Workflow chain

```text
Roadmap (ROADMAP.md)
  → GitHub Milestone (P0–P9)
    → GitHub Issue (scope, acceptance criteria)
      → Branch (one issue)
        → Implementation
          → Tests
            → Pull Request (template)
              → Review
                → CI (when present)
                  → Merge
                    → Release tag OR Experiment report
```

---

## Roles of artifacts

| Artifact | Purpose |
|----------|---------|
| `ROADMAP.md` | Phase gates, exit criteria, active phase |
| GitHub Milestone | Phase bucket for issues |
| GitHub Issue | **Scope boundary** for one unit of work |
| Branch / PR | Implementation and review record |
| `docs/DECISION_LOG.md` | Durable architectural/product decisions |
| `docs/RISK_REGISTER.md` | Tracked risks and mitigation status |
| `docs/EXPERIMENT_TEMPLATE.md` | Research outputs |
| `docs/incidents/` | S1/S2 postmortems |
| `docs/runbooks/` | Repeatable operational procedures |
| Tests | Executable specification of behavior |
| `CHANGELOG.md` | User-visible and governance changes |

---

## Chat and scope discipline

- **One chat session → one issue** (default).
- New topics discovered mid-task → **new issue**, not added to current PR.
- Important decisions during chat → issue comment or `DECISION_LOG.md` entry before merge.
- Agents must read `AGENTS.md` and `ROADMAP.md` at task start.

---

## WIP limits

| Rule | Limit |
|------|-------|
| Large issues in progress | **1** at a time |
| Small urgent bug (S1/S2) | **+1** optional |
| Open half-done branches | Avoid; merge or close within reasonable time |
| Live/micro-live work | **0** until P8 approved |

---

## Bugfix process

### Steps

1. **Capture** — GitHub issue (`bug` template), label `type:bug`, severity label.
2. **Severity** — S1–S4 (below).
3. **Reproduce** — minimal steps or failing test.
4. **Impact** — positions, PnL, research validity, security.
5. **Regression test** — add before or with fix.
6. **Minimal fix** — no drive-by refactors.
7. **Run tests** — document commands and results.
8. **Pull request** — link issue, fill security/live checklist.
9. **Review** — independent review when possible.
10. **Verify after merge** — smoke test in target environment if applicable.
11. **Incident** — S1/S2: file under `docs/incidents/` using template.
12. **Invalidate research** — if bug affected backtest/paper results, label `status:invalidated` and list affected experiment IDs.

### Severity definitions and responses

| Level | Examples | Response |
|-------|----------|----------|
| **S1 Critical** | Wrong orders, wrong positions, capital risk, state corruption, security | **Stop** affected operation immediately; incident doc; no merge without explicit recovery plan |
| **S2 High** | Wrong PnL, reconciliation break, duplicate fills, unreliable risk limits | **No scaling**; prioritize fix; incident if production impact |
| **S3 Medium** | Wrong backtest, bad data import, invalid research without direct capital risk | Block affected experiments; invalidate results |
| **S4 Low** | Dashboard, copy, minor docs | Normal backlog |

---

## Research workflow

1. Open `research-experiment` issue with hypothesis and accept/reject criteria.
2. Freeze dataset version and config before OOS.
3. Run experiment; fill `docs/EXPERIMENT_TEMPLATE.md` (store under `docs/strategies/` or linked artifact path).
4. Decision: accept / reject — never tune on OOS.
5. PR only for code/config changes required by the experiment; results linked in issue.

See `docs/STRATEGY_LIFECYCLE.md`.

---

## Releases

- **Baseline release (P1):** tag + documented commands; no trading logic change.
- **Paper deploy:** Railway services per `docs/railway-paper-trading-dashboard-v1.md`; config-as-code under `deploy/railway/`.
- **Live release:** **Not applicable** until P8 human approval.

---

## GitHub Project (v2) — manual setup

Automated creation is attempted by `scripts/github_project_setup.py` when `gh` is authenticated with project permissions. If automation skips or fails, create manually:

### Project name

`Trading System Roadmap`

### Status field (single select)

`Backlog` · `Ready` · `In Progress` · `Review` · `Blocked` · `Done`

### Custom fields

| Field | Type | Notes |
|-------|------|-------|
| Phase | Single select | P0–P9 |
| Type | Single select | bug, feature, research, operations, documentation, incident |
| Area | Single select | data, research, strategy, risk, execution, accounting, monitoring, dashboard, infrastructure, security, governance |
| Severity | Single select | S1–S4 (bugs/incidents) |
| Priority | Single select | e.g. P0, P1, P2, P3 |
| Strategy | Text | Strategy name if applicable |
| Release | Text | Target baseline or deploy |

### Suggested views

1. **Current Work** — Status = In Progress OR Review
2. **Roadmap** — group by Phase
3. **Bugs and Incidents** — Type = bug OR incident
4. **Research Pipeline** — Type = research
5. **Risks and Blockers** — label `status:blocked` OR `status:needs-decision`
6. **Completed** — Status = Done

### Link repository

In GitHub: **Projects → New project → Board/Table → Link repo issues**.

Add issues from milestones created by setup script.

---

## GitHub automation script

```bash
# Preview only (no GitHub writes)
python scripts/github_project_setup.py --dry-run

# Create missing labels, milestones, seed issues
python scripts/github_project_setup.py --apply

# One-time duplicate repair (configured list only)
python scripts/github_project_setup.py --repair-duplicates --dry-run
python scripts/github_project_setup.py --repair-duplicates --apply
```

Requirements: [GitHub CLI](https://cli.github.com/) (`gh`) installed and authenticated (`gh auth login`).

**Idempotency guarantees:** Sequential idempotency is covered by automated tests.
Official apply runs are serialized through GitHub Actions concurrency
(`.github/workflows/github-governance-setup.yml`). Uncoordinated parallel local
apply processes are not claimed to be fully atomic.

The normal setup script **never** closes issues, deletes labels/milestones,
changes branch protection, or touches secrets. The explicit
`--repair-duplicates` mode comments and closes only the configured duplicate list.

If `gh` is unavailable, perform label/milestone/issue creation manually using lists in `scripts/github_project_setup.py` source.

---

## Definition of Done

All work must satisfy `docs/DEFINITION_OF_DONE.md` before merge unless explicitly waived in the issue with rationale.

### Pull request review (binding)

Reviewers **must request changes** when:

- The PR omits executed test commands and results (or a justified exception)
- Acceptance criteria are not addressed
- The DoD section is checked without supporting evidence in the PR body

See `docs/DEFINITION_OF_DONE.md` § Review policy (adopted).

---

## Related documents

- `AGENTS.md` — agent rules
- `ROADMAP.md` — phases
- `docs/ARCHITECTURE.md` — system map
- `docs/runbooks/README.md` — operational procedures (stubs)
- `docs/incidents/README.md` — incident index
