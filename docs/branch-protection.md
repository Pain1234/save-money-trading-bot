# Branch Protection on `main`

**Issue:** #65  
**Branch:** `main` (GitHub default since Issue #64, 2026-07-14)  
**Workflow:** `.github/workflows/ci.yml`

## Required status checks

These job `name` values from CI must pass before merging a PR into `main`:

| Check | Job | Purpose |
|-------|-----|---------|
| `validate` | `validate` | Python compile, issue templates, governance tests, PR whitespace |
| `requirements-baseline` | `requirements-baseline` | Portable `requirements-baseline.txt` install |
| `lint` | `lint` | `ruff check .` |
| `test` | `test` | Unit tests (excludes deploy, postgres, live, soak) |
| `test-market-data` | `test-market-data` | `tests/market_data -m "not live"` |
| `test-deploy` | `test-deploy` | Dashboard build + bundle checks (Node 22) |
| `postgres` | `postgres` | PostgreSQL integration tests (`-m "postgres and not soak"`) |

**Not required:** `github-governance-setup.yml` `validate` job — runs only when governance
paths change, not on every PR.

## Protection rules

| Rule | Setting |
|------|---------|
| Require pull request before merging | Yes |
| Required status checks | All seven CI checks above |
| Require branches to be up to date | Yes (strict) |
| Required reviewers | None (solo maintainer per ADR-011) |
| Allow admin bypass | Yes (maintainer emergency merge) |

## Solo-maintainer review (ADR-011)

Self-review on PR is acceptable when CI is green and scope matches a linked issue.
Merge is blocked when any required check fails.

## Verify settings

```bash
gh api repos/Pain1234/save-money-trading-bot/branches/main/protection
```
