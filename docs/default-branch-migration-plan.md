# Default Branch Migration Plan (`main`)

**Issues:** #52 (plan), #64 (execution)
**Status:** **Executed** (2026-07-14) — GitHub default branch is `main`
**Previous default branch:** `cursor/railway-paper-dashboard-v1` (retained for rollback)
**Migration commit:** `10000d3bb052d6a04e680f2466e8ab97274c4163` (`baseline-paper-v1.0.1`)

This document records the migration from the Cursor/feature-named default branch to a
stable `main` branch.

---

## Current state (2026-07-14, post-migration)

| Item | Value | Source |
|------|-------|--------|
| GitHub default branch | `main` | `gh repo view` |
| Rollback branch | `cursor/railway-paper-dashboard-v1` (same SHA as `main` at cutover) | `git branch -a` |
| Open pull requests | None | `gh pr list --state open` |
| Production deploy platform | Railway (four services) | `docs/railway-paper-trading-dashboard-v1.md` |
| Public dashboard URL | `https://bot.save-money.xyz` | Railway custom domain |
| DNS / edge | Cloudflare (domain `save-money.xyz`) | **Not configured in repository** — verify in Cloudflare dashboard |

Railway service config files (`deploy/railway/*.toml`) do **not** pin a Git branch;
the deployed branch is set in the **Railway project → service → Settings → Source**
UI. Confirm the active branch before migration.

---

## Deployment branch verification checklist

Before changing the GitHub default branch, a maintainer must record:

- [ ] **Railway worker** (`paper-trading-worker`) — deployed branch: _____________
- [ ] **Railway API** (`paper-trading-api`) — deployed branch: _____________
- [ ] **Railway dashboard** (`paper-trading-dashboard`) — deployed branch: _____________
- [ ] **Cloudflare DNS** — `bot.save-money.xyz` CNAME/proxy target matches Railway networking (see `docs/railway-paper-trading-dashboard-v1.md` § Domain)

**Expected today:** all Railway services track `cursor/railway-paper-dashboard-v1`
(the GitHub default). Re-verify in the Railway UI; do not assume from repo artifacts.

Cloudflare does not deploy application code for this project. DNS/proxy changes are
independent of the Git branch name unless Page Rules or Workers are involved — confirm
none apply to `bot.save-money.xyz`.

---

## Target state

| Item | Target |
|------|--------|
| GitHub default branch | `main` |
| Target commit | Tip of `cursor/railway-paper-dashboard-v1` at migration time (same SHA on both branches) |
| Railway services | Continue deploying from `main` after cutover |
| Stale branch | `cursor/railway-paper-dashboard-v1` retained (not deleted) for rollback |

### Create `main` (when approved)

```bash
git fetch origin
git checkout cursor/railway-paper-dashboard-v1
git pull origin cursor/railway-paper-dashboard-v1
git branch main
git push -u origin main
```

Then change the GitHub default branch to `main` (Settings → Branches → Default branch).

---

## Migration steps (human approval required)

1. **Freeze merges** briefly; confirm no open PRs target the old default (or retarget them).
2. **Verify Railway** services deploy from the intended branch; note current commit SHA.
3. **Create `main`** at the same commit as `cursor/railway-paper-dashboard-v1` (see above).
4. **Update Railway** source branch to `main` for worker, API, and dashboard (one service at a time or all together after smoke check).
5. **Change GitHub default** to `main` (requires admin).
6. **Enable branch protection** on `main` with required status checks from `.github/workflows/ci.yml`:
   - `validate`
   - `lint`
   - `test`
   - `test-market-data`
   - `test-deploy`
   - `postgres`
7. **Update local clones:** `git remote set-head origin main`
8. **Document** migration date and commit SHA in `CHANGELOG.md`.

---

## Rollback plan

If migration causes deploy or CI regressions:

1. **Railway:** revert each service source branch to `cursor/railway-paper-dashboard-v1` and redeploy last known-good deployment.
2. **GitHub:** change default branch back to `cursor/railway-paper-dashboard-v1`.
3. **Branch protection:** disable or relax on `main` until root cause is fixed.
4. **Do not delete** either branch until production is stable for at least one release cycle.

Rollback does not require rewriting history if `main` was created as a pointer to the
same commit (fast-forward only).

---

## Open PR bases

At plan time (2026-07-14): **no open pull requests**. Before migration, re-run:

```bash
gh pr list --state open --json number,baseRefName,headRefName
```

Any PRs targeting `cursor/railway-paper-dashboard-v1` must be merged, closed, or
retargeted to `main` after the default branch change.

---

## Branch protection plan (post-migration)

CI workflow: `.github/workflows/ci.yml` (Issue #53).

| Required check | Job | Purpose |
|----------------|-----|---------|
| `validate` | `validate` | Python compile, issue templates, governance tests, `git diff --check` |
| `lint` | `lint` | `ruff check .` |
| `test` | `test` | Unit tests (excludes deploy, postgres, live, soak) |
| `test-market-data` | `test-market-data` | `tests/market_data -m "not live"` |
| `test-deploy` | `test-deploy` | Dashboard build + bundle checks (Node 22) |
| `postgres` | `postgres` | PostgreSQL integration tests (`-m "postgres and not soak"`) |

**Status (2026-07-14):** Branch protection on `main` tracked in Issue #65. See
`docs/branch-protection.md` for required checks after #65 execution.

**Solo-maintainer review process (ADR-011):** self-review on PR is acceptable when
CI is green and scope matches a linked issue; merge blocked when any required check
fails.

Branch protection is configured on `main` per Issue #65 after migration.

---

## Migration execution record (#64)

| Step | Status |
|------|--------|
| Create `main` at same SHA as old default | Done (`10000d3`) |
| Change GitHub default branch to `main` | Done |
| Retain `cursor/railway-paper-dashboard-v1` for rollback | Done |
| Railway source branch → `main` | **Manual verification pending** (see checklist below) |
| Cloudflare DNS unchanged | **Manual verification pending** |
| Branch protection (#65) | See `docs/branch-protection.md` |

### Human approval gate (completed for GitHub cutover)

- [x] Target commit SHA agreed (`10000d3` = `baseline-paper-v1.0.1`)
- [x] Rollback plan reviewed
- [ ] Railway deployment branches verified and recorded (manual)
- [ ] Cloudflare DNS verified (manual)
