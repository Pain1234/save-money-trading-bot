# Incident Report Template

Blameless post-incident documentation. Copy to `docs/incidents/INC-YYYYMMDD-NNN-title.md`.

---

```text
Incident-ID:
Titel:
Schweregrad: S1 | S2 | S3
Status: active | mitigated | resolved | postmortem-complete

Beginn:
Erkannt:
Beendet:

betroffene Version: (git tag or commit)
betroffene Umgebung: local | railway-paper | other

Zusammenfassung:

Auswirkung:
  capital:
  positions:
  data:
  research:

Erkennung: (alert, user report, reconciliation, test)

Zeitlicher Ablauf:
  (timeline with UTC timestamps)

Technische Ursache:

Beitragende Faktoren:

Sofortmaßnahmen:

Daten- oder Kontokorrektur:

Dauerhafte Schutzmaßnahmen:

Ergänzte Tests:

Betroffene Experimente: (IDs or "none")

Zugehörige Issues und Pull Requests:

Lessons Learned:
```

---

## Guidelines

- Facts and timelines first; avoid naming individuals for blame.
- Separate **detection**, **response**, and **remediation** sections.
- Every S1 should link at least one regression test or explicit gap issue if test impossible.
- If research invalidated, list experiment IDs and update `docs/strategies/README.md`.
