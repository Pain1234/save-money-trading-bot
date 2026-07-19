# Research Workspace UI Spec — Hyperliquid-Style Shell

**Status:** Binding visual contract for P4.9 UI epic

**Reference image:** [`research-workspace-hyperliquid-reference.png`](./research-workspace-hyperliquid-reference.png)

**Milestone:** P4 – Research Engine und Research Workspace V1

**Related:** Epic P4.9 UI (Hyperliquid-Style Research Workspace); data epic [#295](https://github.com/Pain1234/save-money-trading-bot/issues/295) (Regime Scorecard)

The reference PNG is a **visual implementation target only**. It must never be
shipped as an app background, public asset route, or production data source.

**Provenance (Public Core):** The file is a **fully synthetic wireframe** generated
by `scripts/generate_research_workspace_ui_reference.py`. It contains only
placeholder labels (`demo`, `Nicht verfuegbar`, regime names like `trend_up`) —
no real usernames, run/experiment IDs, configs, error payloads, or production
metrics. Safe under `docs/governance/PUBLIC_PRIVATE_BOUNDARY.md`. Regenerate
with:

```bash
python scripts/generate_research_workspace_ui_reference.py
```

---

## 0. Preflight inventory (before UI-01)

Captured 2026-07-18 against `origin/main` SHA
`2c7f404336fee56ddf05c88cb040007db6d03e2f` (Merge PR #283 / Research E2E).

### Active work (do not overwrite)

| Branch / PR | Notes |
|-------------|--------|
| `fix/research-symbol-constraints` (local primary checkout) | Unrelated WIP; 48 commits behind `main`; leave untouched |
| PR [#279](https://github.com/Pain1234/save-money-trading-bot/pull/279) `#278` | Lab job-only detail crash — **CONFLICTING** with `main` |
| PR [#296](https://github.com/Pain1234/save-money-trading-bot/pull/296) `#284` | P4.9 scorecard contract docs — MERGEABLE / blocked on checks |
| Epic [#295](https://github.com/Pain1234/save-money-trading-bot/issues/295) | P4.9 Regime Scorecard (data/API) — distinct from this UI epic |

UI work ships on `feat/298-research-shell` from `origin/main`
via a dedicated worktree so symbol-constraint WIP is never mixed in.

### P4 workspace issues (#245–#250)

| Issue | State |
|-------|-------|
| #245 Durable Research Jobs | CLOSED |
| #246 Experiment Comparison | CLOSED |
| #247 Robustness | CLOSED |
| #248 Gates | CLOSED |
| #249 Validation Studies | CLOSED |
| #250 Research E2E / UI-Abnahme | OPEN (Playwright waiver; API E2E landed) |
| #242 Strategy Lab UI-Abnahme | OPEN |
| #295 / #284–#293 Regime Scorecard | OPEN (docs PR #296) |

### Active Research routes (`src/app/dashboard/research/`)

| Route | Purpose |
|-------|---------|
| `/dashboard/research` | Overview |
| `/dashboard/research/strategies` | Strategy catalog |
| `/dashboard/research/strategies/[strategyId]` | Strategy detail |
| `/dashboard/research/experiments` | Experiment list |
| `/dashboard/research/experiments/new` | Strategy Lab |
| `/dashboard/research/experiments/[experimentId]` | Experiment detail + charts |
| `/dashboard/research/compare` | Run compare |
| `/dashboard/research/robustness` | Robustness list / create |
| `/dashboard/research/robustness/[robustnessId]` | Robustness detail |
| `/dashboard/research/validation` | Validation studies list |
| `/dashboard/research/validation/[studyId]` | Study detail |

### Existing UI components (`src/components/research/`)

`CompareView`, `ExperimentJobPanel`, `ExperimentsTable`, `ResearchCharts`,
`ResearchTradeChart`, `RobustnessCreateForm`, `RobustnessJobPanel`,
`RobustnessManifestView`, `RobustnessTable`, `StrategiesCatalogView`,
`StrategyDetailView`, `StrategyLabForm`, `ValidationStudiesTable`,
`ValidationStudyCreateForm`, `ValidationStudyDecisionPanel`,
`ValidationStudyDetailView`.

### Existing chrome (shared with Monitor)

- Auth boundary: `src/app/dashboard/layout.tsx` → `requireAuth()`
- `Navbar` + `Sidebar` branch on `isResearchPath()` today (dual chrome in one shell)
- Tokens: `src/styles/design-tokens.css` + `src/app/globals.css` (Monitor design-freeze in `docs/design-system.md`)
- Nav: `src/lib/research/navigation.ts` (`WORKSPACE_NAV`, `RESEARCH_NAV`)

### API surface already on `main` (`src/lib/research-api/client.ts`)

Present: overview, experiments list/detail, compare, robustness list/detail,
gates list, validation studies list/detail, lab/job types, integrity fields,
metrics + equity/drawdown series, trade chart helpers.

### Missing data fields for gate-first / scorecard UI (UI-02 / UI-03)

Not yet on the Research read API (tracked under #295 / #284–#293):

- Regime scorecard / regime table rows
- Evidence confidence / sample sufficiency profile
- Worst-regime profile
- Transition matrix
- Parameter plateau / local stability surface
- Cost-stress scorecard slice (beyond existing robustness job UI)
- Executive “Final Decision” bound to scorecard (Validation Study decision exists; scorecard binding does not)
- Trade forensics: MFE/MAE, fold drilldowns as first-class panels (UI-05)
- Dedicated gate-history timeline UI (gates API exists; dense forensics panel does not)

**Missing-data rule:** render `Nicht verfügbar` / explicit empty panels — never invent metrics.

### Merge-conflict risks

- Do not land UI changes on `fix/research-symbol-constraints`
- Rebase/conflict likely with PR #279 on `experiments/[experimentId]/page.tsx` and `client.ts`
- Monitor design-freeze: ResearchShell must not alter Monitor layout tokens/order

---

## 1. Zielbild

A professional research and validation console:

- High information density
- Dark Hyperliquid-adjacent surfaces
- Thin borders, compact tables
- Mint/turquoise primary accent
- Red for loss / fail / integrity errors
- Yellow/amber for warnings / incompatible compares
- Gate-first hierarchy (integrity → critical gates → evidence → decision)
- No marketing hero, no oversized SaaS cards, no fabricated production data

Single Research Workspace — no second registry, engine, or trading/promotion UI.

---

## 2. Layoutsystem

### Shell split

```text
DashboardLayout (Server) — requireAuth() only
  └── DashboardChrome (Client) — usePathname()
        ├── /dashboard/research* → ResearchShell
        └── other /dashboard*    → MonitorShell (existing Navbar + Sidebar + Footer)
```

Never render two navbars or two sidebars at once.

### ResearchShell (full-width)

| Zone | Role |
|------|------|
| Topbar | Brand, Monitor/Research switch, user/logout |
| Market ticker | Research universe strip (no live price invention) |
| Compact sidebar | `RESEARCH_NAV` only |
| Main | Route children |
| Footer | Compact research disclaimer |

Monitor shell keeps `max-w-[1600px]` padded layout from design-freeze.
Research shell may go full viewport width with denser gutters.

---

## 3. Farben

Reuse Monitor tokens where possible (`--ds-color-*`). Research-scoped overrides
live under `.research-shell` (`--rs-*`) and must not mutate Monitor freeze values.

| Role | Token / value |
|------|----------------|
| Base | `--ds-color-bg-base` `#060e14` |
| Panel | `--ds-color-bg-card` `#0a151d` |
| Border | `--ds-color-border` thin |
| Accent | `--ds-color-mint` `#42d98b` |
| Loss / fail | `--ds-color-negative` `#f05252` |
| Warning | `--ds-color-warning` `#d9a72e` |

---

## 4. Typografie

| Use | Style |
|-----|--------|
| UI labels | Sans (`--ds-font-sans`), 11–13px, muted for keys |
| IDs / hashes / JSON / table values | Mono (`--ds-font-mono`) |
| Section titles | 13–14px semibold, not hero marketing sizes |
| Sidebar title | Compact (≤18px) — not 26px Monitor hero |

---

## 5. Spacing

| Token | Research default |
|-------|------------------|
| Shell padding | 10–14px |
| Sidebar width | ~188–220px |
| Panel radius | 2–4px (`--rs-radius`) |
| Table row | Tight (py-1 / py-1.5) |
| Panel gap | 8–12px |

---

## 6. Komponenten

| Component | File | Notes |
|-----------|------|-------|
| `DashboardChrome` | `src/components/layout/DashboardChrome.tsx` | Path switch |
| `MonitorShell` | `src/components/layout/MonitorShell.tsx` | Preserves Monitor chrome |
| `ResearchShell` | `src/components/research/shell/ResearchShell.tsx` | Full research chrome |
| `ResearchTopbar` | `…/ResearchTopbar.tsx` | Workspace switch + session |
| `ResearchTicker` | `…/ResearchTicker.tsx` | Universe strip; no fake ticks |
| `ResearchSidebar` | `…/ResearchSidebar.tsx` | Compact `RESEARCH_NAV` |

UI-02 (#299): `ExecutiveGateStrip` + `ResearchOverviewView` on
`/dashboard/research` — gate-first hierarchy; scorecard-only fields stay
`Nicht verfügbar` until #291/#295.

UI-03 (#300): reusable `src/components/research/analytics/*` panels
(Regime table, Equity vs Benchmark, Underwater, Transition, Plateau,
Cost Stress, Evidence Summary). Empty until #291; detail binding in #292.

UI-04 (#292): `ScorecardBindSection` + `ScorecardProfileStrip` bind
`GET /api/v1/research/scorecards` / `{id}` on Validation Study, Experiment,
and Strategy detail. Maps `global_profile` (integrity, gates, worst regime,
transition risk_label, parameter classification, confidence, weakness).
`NOT_AVAILABLE` → `Nicht verfügbar`. Study binding uses the **primary run** only and requires a sealed
`evidence_snapshot.scorecards[]` pin hash — never falls back to unpinned
`GET /scorecards?run_id=` registry hits. Invalidated scorecards and
`evidence_integrity.ok=false` / pin hash mismatch → fail-closed
error/unavailable (no ready profile). Regime table rows remain unavailable
until per-regime metrics are exposed on the scorecard GET payload
(`regime_metrics.json` is not inlined). No promotion controls.

UI-05 (#301): Robustness, Validation, and remaining Research routes adopt
`ResearchPageChrome` dense tokens (`rs`, `ResearchPageHeader`, `ResearchTableFrame`,
`ResearchApiError`, `ResearchLoadingSkeleton`, `ResearchNotFound`) — aligned with
Overview / ResearchShell typography; Monitor Card styling unchanged.

**Rest scope (explicit, not in this PR):** Evidence Inputs inventory,
Gate Failures detail list, and clickable Raw Metric Refs into run artifacts
are deferred until those fields are exposed on the scorecard/read API (or a
follow-up UI issue). Cost-stress boundary and full transition matrix likewise
remain Nicht verfügbar when absent from Layer-5.

UI-05 (#301): Shared `ResearchPageChrome` (`rs` tokens, page header, API
error, empty, loading skeleton, table frame, not-found) densifies Strategies,
Experiments, Lab, Compare, Robustness, and Validation routes to match
ResearchShell typography (18px titles, 12px body, `rounded-sm`). No new
routes; API wiring unchanged; Monitor shell untouched.

---

## 7. Responsive-Verhalten

| Viewport | Behavior |
|----------|----------|
| Desktop ≥1280 | Sidebar + main |
| Laptop | Narrower sidebar; ticker scrolls horizontally |
| Tablet | Collapsible sidebar / drawer; topbar persists |
| Mobile review | Stacked; nav as select or drawer; tables horizontal-scroll |

UI-06 owns Playwright + screenshot acceptance across breakpoints.

---

## 8. Statussemantik

| State | Color | Examples |
|-------|-------|----------|
| Pass / complete / active nav | Mint | `completed`, integrity ok |
| Fail / loss / integrity error | Red | `failed`, negative PnL, diff highlights |
| Warning / incompatible | Yellow | Compare identity mismatch, partial child failures |
| Missing | Muted gray text | `Nicht verfügbar` |

---

## 9. Datenquellen

| Surface | Source |
|---------|--------|
| Overview / experiments / charts | Existing Research API |
| Compare / robustness / validation / gates | Existing endpoints on `main` |
| Regime scorecard / evidence confidence | `GET /scorecards`, `GET /scorecards/{id}` (#291) bound in UI (#292) |
| Monitor paper data | Unchanged paper API |

No second Research surface or registry.

---

## 10. Missing-Data-Regeln

1. Null / absent → `Nicht verfügbar` (never `0` unless zero is proven).
2. Scorecard panels without API → empty/unavailable panel with reason, not mock numbers.
3. Ticker shows instrument universe labels only until a real read-only feed exists.
4. Reference PNG must not be imported into Next.js public/static runtime bundles for UI chrome.

---

## 11. Accessibility

- Landmark roles: `banner`, `navigation`, `main`, `contentinfo`
- Keyboard: all nav links focusable; visible focus rings
- `aria-current="page"` on active Research nav items
- Contrast: mint/red/yellow on dark base meets WCAG AA for text ≥12px where feasible
- Screenreader labels on workspace switch and ticker (`aria-label`)
- Do not rely on color alone for pass/fail (include text status)

---

## 12. Screenshots der fertigen Umsetzung

| Shot | Path (UI-06) | Notes |
|------|----------------|-------|
| Style reference (pre-rebuild) | `docs/design/research-workspace-hyperliquid-reference.png` | Density / color / chrome target |
| Shell desktop | `docs/visual-regression/research-shell-desktop.png` | After UI-01 |
| Overview gate-first | `docs/visual-regression/research-overview-gates.png` | After UI-02 |
| Regime / analytics | `docs/visual-regression/research-regime-scorecard.png` | After UI-03 |
| Mobile review | `docs/visual-regression/research-shell-mobile.png` | After UI-06 |

Until UI-06 lands, only the style reference PNG is required in-repo.

---

## 13. Dependency chain

```text
UI-01 Shell + Design System (Ready first)
  → UI-02 Overview / Executive Gates
  → UI-03 Regime Scorecard + Analytics
  → UI-04 Unify all research routes
  → UI-05 Forensics / Audit drilldowns
  → UI-06 Responsive / a11y / E2E acceptance
```

Coordinate with data epic #295: UI-02/UI-03 must degrade gracefully until
scorecard API fields exist.

---

## 14. GitHub tracking

| Slice | Issue |
|-------|-------|
| Epic | [#297](https://github.com/Pain1234/save-money-trading-bot/issues/297) |
| UI-01 Shell (Ready) | [#298](https://github.com/Pain1234/save-money-trading-bot/issues/298) |
| UI-02 Overview | [#299](https://github.com/Pain1234/save-money-trading-bot/issues/299) |
| UI-03 Regime / Analytics | [#300](https://github.com/Pain1234/save-money-trading-bot/issues/300) |
| UI-04 Unify routes | [#301](https://github.com/Pain1234/save-money-trading-bot/issues/301) |
| UI-05 Forensics | [#302](https://github.com/Pain1234/save-money-trading-bot/issues/302) |
| UI-06 Acceptance | [#303](https://github.com/Pain1234/save-money-trading-bot/issues/303) |
