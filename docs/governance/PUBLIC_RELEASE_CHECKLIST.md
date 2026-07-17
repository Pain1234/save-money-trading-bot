# Public-release checklist

Human gate for intentional public-core publication or visibility changes.
Epic: **#176**. Security audit: **#177**.

Repository visibility alone is not this checklist. Complete and record approval on the governing issue before treating a public release as accepted.

## Preconditions

- [ ] [PUBLIC_PRIVATE_BOUNDARY.md](PUBLIC_PRIVATE_BOUNDARY.md) reviewed
- [ ] License and contribution policy decided (#178)
- [ ] Public disclaimer present in README (#179)
- [ ] Private-edge extension direction documented (#180)
- [ ] Security audit recorded (#177) — see [SECURITY_AUDIT_PUBLIC_RELEASE.md](SECURITY_AUDIT_PUBLIC_RELEASE.md) — findings fixed or accepted in writing

## Content scan

- [ ] No exchange API keys, session secrets, or account identifiers in tree
- [ ] No private research results, rankings, or optimized parameter dumps
- [ ] No production deployment secrets in tracked files
- [ ] Examples use placeholders only (no real secret names that imply live keys)
- [ ] Artifact examples under `examples/` are synthetic / public-safe

## Process

- [ ] Explicit human approval comment on #176 (or successor release issue)
- [ ] No automated workflow flips visibility or copies private repos
- [ ] Public CI remains self-contained (no private checkout)

## Record

After approval, note: approver, date, commit SHA, and link to audit (#177) on the issue.
