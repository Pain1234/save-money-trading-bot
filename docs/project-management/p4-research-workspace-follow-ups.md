# P4 Research Workspace — follow-up issues

Governance sync: [#244](https://github.com/Pain1234/save-money-trading-bot/issues/244).
Milestone: **P4 – Research Engine und Research Workspace V1**.

## Dependency chain (actual)

```text
#240 read-only (done)
  → #242 Strategy Lab + start (PR #243 merged; UI-Abnahme noch offen)
    → #245 P4.6b Durable Job Execution / Restart Recovery
      → #246 P4.7a Compare
      → #247 P4.7b Robustness orchestration
        → #248 P4.7c Gate Evaluator + persistence
          → #249 P4.7d Validation Studies API + UI
            → #250 P4.8 E2E / Repro / UI-Abnahme
              → P4 exit (honest) → P5 usable enough
```

Cancel / Retry / Re-run remain **bewusst zurückgestellt** (kein Issue in diesem Sync).

P5 Strategy-V1 execution uses P4.7b/d infrastructure but stays on P5 issues (#251–#255, #204, #205).

---

## Delivered / in acceptance

| Item | Issue | Status |
|------|-------|--------|
| Read-only Overview / list / detail | [#240](https://github.com/Pain1234/save-money-trading-bot/issues/240) | **abgeschlossen** |
| Strategy Lab + start (in-process jobs) | [#242](https://github.com/Pain1234/save-money-trading-bot/issues/242) / PR [#243](https://github.com/Pain1234/save-money-trading-bot/pull/243) | **technisch umgesetzt, aber noch nicht abgenommen** (manuelle UI-Abnahme mit Dataset-Katalog ausstehend) |

**V1 job limit (until #245):** in-process threads do not resume after API process restart; stale `queued`/`running` fail-closed on the next status read.

---

## Open follow-ups (real issues)

### [#245](https://github.com/Pain1234/save-money-trading-bot/issues/245) — P4.6b Durable Research Job Execution und Restart Recovery

Persistenter Jobstatus, Restart-/Orphan-Verhalten, Status-API. Keine neue Backtest Engine; keine Live-Orders.

### [#246](https://github.com/Pain1234/save-money-trading-bot/issues/246) — P4.7a Experiment- und Strategie-Vergleich

Compare View; `ExperimentRegistry.compare`-Semantik; keine irreführenden Inkompatibilitätsvergleiche; kein P7-Ranking.

### [#247](https://github.com/Pain1234/save-money-trading-bot/issues/247) — P4.7b Robustness-Orchestrierung

Walk-Forward, Cost Stress, Parameter Stability, Bootstrap/MC orchestrieren + UI. Keine zweite Engine; keine privaten P5-Ergebniswerte im Public Repo.

### [#248](https://github.com/Pain1234/save-money-trading-bot/issues/248) — P4.7c Versionierter Gate Evaluator und Gate-Persistenz

Policy-Version, Gate-Name, Grenzwert, Messwert, Pass/Fail, Reason, Persistenz. Keine Auto-Promotion.

### [#249](https://github.com/Pain1234/save-money-trading-bot/issues/249) — P4.7d Validation Studies API und UI

Routen `/dashboard/research/validation` und `/dashboard/research/validation/[studyId]`. Public Core nur generisch/synthetisch; echte P5-Ergebnisse privat (#181). P5 registriert die Strategy-V1-Studie separat als [#255](https://github.com/Pain1234/save-money-trading-bot/issues/255).

### [#250](https://github.com/Pain1234/save-money-trading-bot/issues/250) — P4.8 Research E2E, Reproduzierbarkeit und UI-Abnahme

Lab→Run→Detail, Compare, Robustness, Validation Study, Fehler/Restart/Doppelstart, CLI-Kompatibilität, manuelle UI-Abnahme, Playwright/API-E2E. Schließt auch die offene Abnahme von #242.

---

## Milestone note

P4 is **not** complete while #242 acceptance, #245–#250 (or explicit deferrals), and exit criteria remain open.
P5 planning may proceed; **actual** P5 economic validation remains gated on usable Engine + Workspace and the P5 execution chain.
