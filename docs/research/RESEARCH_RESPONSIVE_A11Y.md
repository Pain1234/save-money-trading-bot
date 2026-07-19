# Research Workspace — Responsive / a11y acceptance (#303)

Evidence checklist for UI-06. Run against paper-api stub + production Next build
(`npm run test:research-smoke`).

## Breakpoints

| Mode | CSS viewport | Expected |
|------|--------------|----------|
| Mobile review | 390×844 | Nav toggle visible; desktop sidebar hidden; tables may scroll inside frames |
| Tablet | 768×1024 | Same as mobile for sidebar (`lg` ≥1024); topbar + ticker persist |
| Laptop | 1280×800 | Persistent sidebar; shell no horizontal overflow |
| Desktop | ≥1280 / 1440×900 | Wider `--rs-shell-x` / sidebar tokens; landmarks present |

Automated: `tests/visual/research-a11y-responsive.spec.ts`.

## Accessibility

| Check | Evidence |
|-------|----------|
| Landmarks `banner`, `navigation` (Workspace + Research), `main`, `contentinfo` | Playwright role assertions |
| Skip link to `#research-main` | `research-skip-link` → `tabIndex={-1}` main `toBeFocused()` |
| `aria-current="page"` on active nav / workspace | Existing shell links |
| Mobile nav `aria-expanded` + Escape closes | Playwright mobile test |
| Visible `:focus-visible` rings (mint) | `.research-shell` tokens in `design-tokens.css` |
| Ticker `aria-label` | `Research instrument universe` |
| Pass/fail not color-only | Status text retained in tables/panels |

## Loading / Error / Empty

Unchanged chrome helpers (`ResearchLoadingSkeleton`, `ResearchApiError`,
empty testids on Overview / lists). Smoke covers empty Overview and list routes
(`research-routes.spec.ts`).

## Screenshots (UI spec §12)

| Shot | Path |
|------|------|
| Shell desktop | `docs/visual-regression/research-shell-desktop.png` |
| Shell mobile | `docs/visual-regression/research-shell-mobile.png` |

Overview-gate / regime-scorecard shots remain optional until a fixture with
bound scorecard detail is available in the stub (do not invent metrics).

## Monitor regression

Workspace switch Research → Monitor must leave `dashboard-page-ready` green
(covered in both research smoke specs).

## Final acceptance cross-link (#250)

BOT 3B 2026-07-19 re-ran `npm run test:research-smoke` (10 passed) and the
full `tests/visual/` suite (28 passed) on SHA `1516ddb…` with Railway deploy
parity. Full matrix + Legacy/READY scenarios:
`docs/research/RESEARCH_WORKSPACE_ACCEPTANCE.md`.
