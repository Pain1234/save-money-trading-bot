# Milestone Coverage Audit

**Date:** 2026-07-17
**Governance issue:** [#244](https://github.com/Pain1234/save-money-trading-bot/issues/244)
**Source of truth:** GitHub milestones/issues/PRs at audit time; documents reconciled afterward.

Status vocabulary used below:

| Status | Meaning |
|--------|---------|
| **geplant** | Phase/Arbeit beschrieben; Umsetzung noch nicht gestartet |
| **implementiert** | Code/Docs geliefert und auf `main` (oder äquivalent gemergt) |
| **technisch umgesetzt, aber noch nicht abgenommen** | Lieferung existiert (PR/Branch/Tests), Exit-/Abnahmekriterien offen |
| **abgeschlossen** | Milestone-/Phase-Exit-Kriterien mit Evidenz erfüllt |
| **blockiert** | Bewusst gestoppt bis Gate/Human Approval |
| **bewusst zurückgestellt** | Explizit deferred (Issue/ADR/ROADMAP) |

Milestone titles are resolved by title in GitHub (not hardcoded by number in process).

---

## Coverage matrix

| Phase | Roadmap vorhanden | Milestone vorhanden | Issues vollständig | Phase-Status (ehrlich) | Lücken |
|-------|-------------------|---------------------|--------------------|------------------------|--------|
| **P0** | Ja | `P0 – Governance and Scope Freeze` | Ja (0 open / 9 closed) | **abgeschlossen** | Keine materiellen Lücken |
| **P1** | Ja | `P1 – Reproducible Baseline Release` | Ja (0 open / 7 closed) | **abgeschlossen** | Post-tag follow-ups historisch (PR #63) |
| **P2** | Ja | `P2 – Operational Reliability` | Teilweise (#11 open) | **implementiert** (Teil) / Exit **nicht** abgeschlossen | Railway non-prod restore (#11); Kill-switch runbook partial |
| **P2.5** | Ja | `P2.5 – Dashboard Performance & Responsiveness` | Seed-Issues **alle closed**, Exit-Kriterien in ROADMAP offen | **geplant** / Status drift | Closed seeds ≠ production acceptance; ROADMAP „Not started“ vs closed issues — nicht als Complete führen |
| **P3** | Ja | `P3 – Versioned Historical Market Data` | Ja (0 open / 11 closed) | **abgeschlossen** | Keine |
| **P4** | Ja (Name drift) | War `P4 – Research Engine` → Zielname Workspace V1 | Engine closed; Workspace #240/#242 zuvor **ohne** Milestone; Follow-ups fehlten als Issues | **technisch umgesetzt, aber noch nicht abgenommen** (Engine + read UI); Lab **in Review** | Durable jobs, Compare, Robustness, Gates, Validation Studies, E2E/UI-Abnahme |
| **P5** | Ja | `P5 – Honest Validation of Trend Strategy V1` | Planung #196–#203/#181 vorhanden; **Ausführungsissues fehlten** | **geplant** (keine echte V1-Validierung ausgeführt) | #200–#203 ≠ Execution; #204-Deps unvollständig; Validation-Study-Tracking fehlte |
| **P6** | Ja | `P6 – Paper Trading Soak` | Nur Epic #46 + #182 | **geplant** (Soak nicht gestartet) | Zerlegung P6-00…P6-06 fehlte |
| **P7** | Ja (Planning only) | `P7 – Multi-Asset and Independent Strategy Candidates` | Planning-Issues vorhanden (10 open) | **geplant** / **bewusst zurückgestellt** bis P5/P6-Gates | Keine neuen Impl-Issues nötig; Zerlegung erst nach Gates |
| **P8** | Ja | `P8 – Separate Micro-Live System` | Boundary-Issue #184 | **blockiert** | Detaillierte Zerlegung erst nach Human Approval |
| **P9** | Ja | `P9 – Controlled Scaling` | Boundary-Issue #185 | **blockiert** | Detaillierte Zerlegung erst nach P8 + Human Approval |

---

## Evidence notes (audit-time)

### P4

| Item | State |
|------|--------|
| Engine (#141–#147, public gates #176–#180, etc.) | **implementiert** / closed under P4 |
| #240 Read-only Workspace | **abgeschlossen** (closed); war ohne Milestone — zuordnen |
| #242 Strategy Lab + start | **offen**; PR [#243](https://github.com/Pain1234/save-money-trading-bot/pull/243) **OPEN** → **technisch umgesetzt, aber noch nicht abgenommen** (manuelle UI-Abnahme + Katalog ausstehend) |
| Compare / Robustness / Gates / Validation Studies / durable restart / E2E | **geplant** — Issues in diesem Governance-Task angelegt |
| Cancel / Retry / Re-run | **bewusst zurückgestellt** |

### P5

| Item | State |
|------|--------|
| #181 public/private | **abgeschlossen** (boundary) |
| #196 entry/freeze | **offen** (human freeze) |
| #197–#199 planning contracts | **abgeschlossen** als Planung |
| #200–#203 | **abgeschlossen** als **Planung/Helfer/Test-Harness** — **nicht** als ausgeführte Strategy-V1-Validierung |
| P5-04E…P5-07E | fehlten → anlegen |
| #204 Final OOS | **blockiert** bis Execution + human pre-OOS |
| #205 Final decision | **geplant** / blocked by #204 |
| P5-10 Validation Study register | fehlte → anlegen (Tracking only) |

### P6

| Item | State |
|------|--------|
| #46 Epic / R-002 | **offen** — darf nicht als einzelnes Mega-Implementierungsissue gelten |
| #182 private telemetry boundary | **offen** |
| Soak start | **nicht gestartet** |
| P6-00…P6-06 | fehlten → anlegen |

### P7–P9

- P7: nur Planning; keine neuen Implementierungsissues in diesem Task.
- P8/P9: **blockiert**; keine Live-/Wallet-/Order-Issues.

### Open PRs (audit-time)

| PR | Topic | Note |
|----|-------|------|
| [#243](https://github.com/Pain1234/save-money-trading-bot/pull/243) | P4.6 Strategy Lab | In Review; dem P4-Milestone zuordnen; #242 nicht vor Merge+Abnahme schließen |
| [#195](https://github.com/Pain1234/save-money-trading-bot/pull/195) | Chore/project governance | Unrelated open PR |

---

## Post-sync checklist (this governance task)

- [x] Matrix published in this file
- [x] P4 milestone renamed + description split delivered/open
- [x] Missing P4/P5/P6 issues created and linked (#245–#262)
- [x] ROADMAP + follow-up docs updated with real issue links
- [x] #47 / #204 / #46 dependency text updated
- [x] No phase falsely marked complete
- [x] No private research metrics published
- [x] #242 reopened until UI-Abnahme documented (PR #243 merged alone insufficient)

### Issue index created in this sync

| # | Title | Milestone |
|---|-------|-----------|
| 244 | Governance sync | P4 |
| 245 | P4.6b Durable jobs | P4 |
| 246 | P4.7a Compare | P4 |
| 247 | P4.7b Robustness | P4 |
| 248 | P4.7c Gate Evaluator | P4 |
| 249 | P4.7d Validation Studies | P4 |
| 250 | P4.8 E2E / UI-Abnahme | P4 |
| 251 | P5-04E Walk-Forward execute | P5 |
| 252 | P5-05E Cost stress execute | P5 |
| 253 | P5-06E Parameter stability execute | P5 |
| 254 | P5-07E Bootstrap/MC execute | P5 |
| 255 | P5-10 Register V1 Validation Study | P5 |
| 256–262 | P6-00…P6-06 | P6 |

### Consciously not created

- P7 implementation decomposition issues
- P8/P9 live/wallet/order/signing implementation issues
- Cancel/Retry/Re-run issues (bewusst zurückgestellt)
- Duplicate issues for #200–#203 execution (new E-suffix issues instead)