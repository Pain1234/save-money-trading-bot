# P2 PR split plan

Split the P2 operational reliability work into **one PR per GitHub issue** (with documented
exception for Issue #15). Do **not** merge as a single branch or mark P2 complete until
Issue #11 restore drill is evidenced.

**Suggested merge order:** #16 → #13 → #14 → #12 → #11 (draft, do not close #11) → #15

---

## Branch map

| Branch | Issue | Files |
|--------|-------|-------|
| `p2/16-metrics` | #16 | `docs/operations/metrics.md` |
| `p2/13-idempotency-audit` | #13 | `docs/operations/idempotency-audit.md` |
| `p2/14-worker-restart` | #14 | `docs/runbooks/worker-restart.md` |
| `p2/12-reconciliation` | #12 | `docs/runbooks/reconciliation-daily.md`, `scripts/reconcile_accounting.py`, `tests/scripts/test_reconcile_accounting.py` |
| `p2/11-backup-restore-draft` | #11 | `docs/runbooks/backup-restore.md`, R-009 row in `docs/RISK_REGISTER.md` |
| `p2/15-runbooks-index` | #15 | `docs/runbooks/README.md`, `deployment-verify.md`, `worker-safe-stop.md`, `kill-switch.md`, `docs/incidents/*`, `ROADMAP.md`, full `docs/RISK_REGISTER.md` |

Each PR adds its own **CHANGELOG** entry under `[Unreleased]`.

---

## Issue #15 bundling note (PR body template)

> This PR bundles three runbooks (`deployment-verify`, `worker-safe-stop`, `kill-switch`)
> plus the runbook index and tabletop incident. **Deviation** from AGENTS.md one-PR-per-runbook:
> index and tabletop require a single coherent pass; kill-switch depends on production
> Railway worker-stop path documented together with safe-stop and deploy-verify.

---

## Create branches (PowerShell)

From a clean `main` with all P2 files present in the working tree, run:

```powershell
.\scripts\split-p2-prs.ps1
git push -u origin p2/16-metrics p2/13-idempotency-audit p2/14-worker-restart p2/12-reconciliation p2/11-backup-restore-draft p2/15-runbooks-index
```

Then open six PRs targeting `main`, each linking its issue.

---

## Exit criteria (not met yet)

- [ ] Issue #11 restore drill executed and recorded in `backup-restore.md`
- [ ] Kill-switch runbook remains **Partial** until production control path is decided
- [ ] ROADMAP P2 status stays **In flight** until all exit boxes checked honestly
