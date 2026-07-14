# INC-20260714-001 — Tabletop duplicate fill scenario

**Type:** Tabletop exercise (no production impact)
**Severity:** S2 (simulated)
**Status:** postmortem-complete

---

```text
Incident-ID: INC-20260714-001
Titel: Tabletop — duplicate fill detected during reconciliation
Schweregrad: S2
Status: postmortem-complete

Beginn: 2026-07-14T10:00:00Z (simulated)
Erkannt: 2026-07-14T10:15:00Z (simulated — daily reconciliation)
Beendet: 2026-07-14T11:00:00Z (simulated)

betroffene Version: baseline-paper-v1.0.0 (daacb627)
betroffene Umgebung: tabletop (railway-paper scenario)

Zusammenfassung:
  Simulated exercise: operator runs weekly reconciliation and discovers wallet cash
  does not match fill-based reconstruction. Hypothesis: worker restart mid-fill
  produced duplicate fill row despite idempotency keys.

Auswirkung:
  capital: none (tabletop)
  positions: simulated — one extra fill row for BTC entry
  data: simulated inconsistency in paper_fills
  research: none

Erkennung: reconciliation (verify_accounting_independent)

Zeitlicher Ablauf:
  10:00Z — Worker OOM kill during fill-at-open job (simulated)
  10:05Z — Worker restarts, recovery marks orphan scheduler run failed
  10:15Z — Weekly reconciliation script reports wallet cash mismatch
  10:20Z — Operator checks /api/v1/status — display_status DEGRADED, heartbeat recovering
  10:30Z — Operator stops worker in Railway (production path; control API disabled)
  10:45Z — Query paper_fills for duplicate deterministic_fill_key (simulated finding)
  11:00Z — Document incident; verify CI tests cover path

Technische Ursache:
  (Simulated) Hypothetical gap: idempotency key collision or bypass — exercise validates
  response process, not a confirmed production bug.

Beitragende Faktoren:
  - Single worker stopped without pre-restart wait
  - Reconciliation run delayed beyond weekly cadence

Sofortmaßnahmen:
  1. Railway — stop `paper-trading-worker` (scale to 0)
  2. Verify via readonly API: /readiness entry_readiness false, heartbeat stale
  3. Preserve Railway logs + DB snapshot reference
  4. Run reconciliation before restart if state suspect

Daten- oder Kontokorrektur:
  (Simulated) Manual delete of duplicate fill row after human review — only with
  backup verified per backup-restore runbook. Not executed in tabletop.

Dauerhafte Schutzmaßnahmen:
  - Confirmed CI coverage: test_restart_lifecycle, test_replay_idempotency
  - Idempotency audit (Issue #13) documents fill path as Covered
  - Weekly reconciliation mandatory (reconciliation-daily runbook)

Ergänzte Tests:
  None required — existing e2e/replay tests already cover duplicate fill prevention.
  Portfolio snapshot postgres test noted as optional enhancement in idempotency audit.

Betroffene Experimente: none

Zugehörige Issues und Pull Requests:
  - Issue #13 (idempotency audit)
  - Issue #14 (worker restart)
  - Issue #12 (reconciliation)
  - P2 operational reliability PR

Lessons Learned:
  1. Reconciliation is the correct detection path for accounting drift.
  2. Kill switch + worker stop order documented in kill-switch and worker-safe-stop runbooks (production: Railway worker stop).
  3. Tabletop validates incident template usability before real S2 event.
  4. Automated CI tests give confidence; production kill still needs runbook discipline.
```

---

## Exercise participants

- Solo maintainer (operator + responder)

## Template compliance

Filled from [`INCIDENT_TEMPLATE.md`](INCIDENT_TEMPLATE.md). P2 ROADMAP exit criterion:
incident template used for tabletop.
