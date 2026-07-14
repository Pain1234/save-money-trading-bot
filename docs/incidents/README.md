# Incidents

Post-incident records for **S1** and **S2** events (and significant S3 if research-wide impact).

Incidents are blameless factual records. They complement GitHub issues labeled `type:incident`.

---

## Index

| Incident-ID | Date | Severity | Title | Status | Report |
|-------------|------|----------|-------|--------|--------|
| INC-20260714-001 | 2026-07-14 | S2 (tabletop) | Duplicate fill reconciliation scenario | postmortem-complete | [INC-20260714-001-tabletop-duplicate-fill.md](INC-20260714-001-tabletop-duplicate-fill.md) |

---

## When to create an incident

- S1: wrong orders/positions, capital risk, state corruption, security breach
- S2: reconciliation break, duplicate fills, sustained wrong PnL, risk limit failure
- S3 (optional): widespread invalid research results

Create a GitHub issue with the `incident` template **and** a markdown file from `INCIDENT_TEMPLATE.md`.

---

## File naming

`docs/incidents/INC-YYYYMMDD-NNN-short-title.md`

---

## Process summary

1. Stabilize (stop worker, freeze entries, preserve logs/DB snapshot if needed).
2. Open incident issue.
3. Fill template during/after response.
4. Link regression tests and permanent fixes in PRs.
5. Update `docs/RISK_REGISTER.md` if new risk identified.

See `docs/PROJECT_OPERATING_SYSTEM.md` bugfix/incident section.
