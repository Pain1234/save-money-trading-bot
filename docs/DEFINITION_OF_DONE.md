# Definition of Done

Checklist before merging any pull request. Copy relevant sections into the PR description.

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
