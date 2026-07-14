# Default Branch Migration Plan (`main`)

**Issue:** #52
**Status:** Plan complete — **default branch NOT changed** (requires explicit human approval)
**Current default branch:** `cursor/railway-paper-dashboard-v1`

This document satisfies the acceptance criteria for planning the migration from the
Cursor/feature-named default branch to a stable `main` branch. It does **not** perform
the migration.

---

## Current state (2026-07-14)

| Item | Value | Source |
|------|-------|--------|
| GitHub default branch | `cursor/railway-paper-dashboard-v1` | `gh repo view` |
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
| `test` | `test` | Unit tests (excludes PostgreSQL, live network, dashboard build) |
| `postgres` | `postgres` | PostgreSQL integration tests (`-m "postgres and not soak"`) |

**Solo-maintainer review process (ADR-011):** self-review on PR is acceptable when
CI is green and scope matches a linked issue; merge blocked when any required check
fails.

Branch protection is **intentionally not enabled** on the current default branch until
this migration is approved and `main` exists.

---

## Human approval gate

The following require explicit maintainer sign-off **before** executing migration steps:

- [ ] Railway deployment branches verified and recorded
- [ ] Cloudflare DNS verified (no unintended Workers/Page Rules on dashboard hostname)
- [ ] Target commit SHA agreed
- [ ] Rollback plan reviewed
- [ ] Window chosen (low-traffic; maintainer available for Railway smoke test)

**Do not change the default branch in automation or via this issue alone.**
