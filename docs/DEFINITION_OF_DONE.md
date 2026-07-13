# Definition of Done

Checklist before merging any pull request. Copy relevant sections into the PR description.

**Binding:** Reviewers must reject PRs that skip test evidence (see [Review policy](#review-policy-adopted)).

---

## General (all changes)

- [ ] Issue has a clear goal and is linked in the PR
- [ ] Scope and non-scope documented in the issue or PR
- [ ] Acceptance criteria met
- [ ] Tests added or justified why none are needed
- [ ] Relevant tests executed successfully (commands listed in PR)
- [ ] Existing tests not disabled without justification
- [ ] Documentation updated (README, docs/, or governance as applicable)
- [ ] No unexplained changes outside issue scope
- [ ] No secrets, credentials, or `.env` contents committed
- [ ] Pull request uses `.github/PULL_REQUEST_TEMPLATE.md`
- [ ] CI successful (when CI exists) or manual checks documented
- [ ] Risks and open points documented in PR
- [ ] Post-merge verification noted if required (deploy, smoke test)

---

## Research changes

Additional requirements when changing or producing strategy/research artifacts:

- [ ] Experiment-ID assigned and recorded
- [ ] Git commit hash documented
- [ ] Dataset version / manifest ID documented
- [ ] Configuration saved (reproducible artifact or pinned file)
- [ ] Cost assumptions documented (fees, slippage, funding if applicable)
- [ ] In-sample and out-of-sample ranges explicitly separated
- [ ] Results reproducible from documented steps
- [ ] Accept or reject decision documented with rationale
- [ ] Prior results not overwritten; invalidation documented if applicable

---

## Bugfixes

- [ ] Root cause documented in issue or PR
- [ ] Reproduction steps or failing test documented
- [ ] Regression test added (or justified exception for S4)
- [ ] Downstream impact assessed (PnL, positions, experiments, versions)
- [ ] Affected experiment IDs or release tags listed if results invalidated
- [ ] S1/S2: incident report planned or filed

---

## Governance / documentation-only

- [ ] No trading logic, strategy parameters, migrations, or production start commands changed
- [ ] YAML/templates validated (syntax)
- [ ] Cross-links to existing specs preserved (no contradictory duplicates)
- [ ] `CHANGELOG.md` updated under `[Unreleased]` when user-facing or structural

---

## Explicit prohibitions (fail DoD if violated)

- Silent strategy parameter changes
- Live trading activation without `human-approval-required` issue
- Risk limit increases without approval
- Undocumented migration or schema change

---

## Review policy (adopted)

Effective with governance rollout (Issue #5, ADR-010).

### Reviewer must verify

1. Linked GitHub issue with acceptance criteria addressed
2. PR template completed (including **Tests → Ausgeführte Befehle und Ergebnis**)
3. At least one executed test command with pass/fail result **or** explicit justification why tests are not required
4. Definition of Done section in PR checked honestly
5. No silent changes to strategy parameters, risk limits, production start commands, or migrations

### Reviewer must reject (request changes) when

- Test section empty with no justification
- Claims "tests pass" without listing commands run
- Scope exceeds linked issue without a separate issue
- DoD checkboxes checked but evidence missing in PR body

### DoD enforcement evidence (Issue #5 — closed, ADR-011)

Governance rollout PR: **#29** (introduced templates and DoD doc).

Three post-governance merged PRs with test evidence (solo-maintainer interim policy, ADR-011):

| PR | Title | Test evidence in body | DoD section in body |
|----|-------|----------------------|---------------------|
| #50 | Risk register top-5 linked | N/A justified (docs + issue creation) | no |
| #54 | Governance idempotency hardening | commands + results listed | no |
| #57 | P0 evidence gaps (architecture CI) | `git diff --check` | yes |

DoD is referenced in the PR template and docs since #29; explicit DoD checklist in the PR body is mandatory from ADR-011 onward (first demonstrated in #57). Formal GitHub review becomes mandatory when a second maintainer is added or a reviewer is assigned. Full pytest CI enforcement tracked in Issue #53.
