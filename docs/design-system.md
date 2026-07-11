# SAVE-MONEY BOT — Design System (Design-Freeze)

**Status:** Verbindlich ab Design-Freeze  
**Version:** 1.0.0  
**Scope:** Mock-Dashboard UI (`bot.save-money.xyz`)

---

## Design-Freeze-Regel

Das folgende ist **eingefroren** und darf in folgenden Sprints **nicht ohne ausdrückliche Anweisung** verändert werden:

- Hauptlayout (`dashboard-shell`, `main-grid`, Sidebar + Main Column)
- Kartenreihenfolge (KPIs → Chart/Markt → Tabellen → Steuerungspanels)
- Größenverhältnisse (CSS-Variablen für KPI/Chart/Panel-Höhen)
- Navigation (Navbar-Links, Active-State, Logo-Position)
- Visuelle Hierarchie (Sidebar-Konzept → Dashboard-Inhalt)
- Responsive Breakpoints und deren Token-Werte

Erlaubt ohne Freigabe: Bugfixes, Backend-/Trading-Logik (separate Sprints), **keine** visuellen Layout-Experimente.

---

## Technische Umsetzung

| Datei | Zweck |
|---|---|
| `src/styles/design-tokens.css` | Zentrale Design-Tokens (Farben, Typo, Spacing, Radii) |
| `src/app/globals.css` | Tailwind-Theme, Layout-Klassen, responsive Overrides |
| `docs/visual-regression/` | Referenz-Screenshots (Playwright) |

---

## Farben

### Surfaces

| Token | Wert | Verwendung |
|---|---|---|
| `--ds-color-bg-base` | `#060e14` | Seitenhintergrund |
| `--ds-color-bg-card` | `#0a151d` | Karten, Panels |
| `--ds-color-bg-card-alt` | `#0e1a24` | Inputs, Diagramm-Knoten |
| `--ds-color-bg-card-hover` | `#101e28` | Hover (selten) |
| `--ds-color-bg-panel` | `#0a151d` | Panel-Flächen |

Tailwind-Aliase: `bg-bg-base`, `bg-bg-card`, `bg-bg-card-alt`

### Borders

| Token | Wert |
|---|---|
| `--ds-color-border` | `rgb(36 52 64 / 0.82)` |
| `--ds-color-border-subtle` | `rgb(28 40 50 / 0.62)` |
| `--ds-color-border-faint` | `rgb(36 52 64 / 0.35)` — Schnellstatistiken-Trennlinien |

### Brand & Status

| Token | Wert | Verwendung |
|---|---|---|
| `--ds-color-mint` | `#42d98b` | Primärakzent, positive Werte, Active Nav |
| `--ds-color-mint-dim` | `#2a9d68` | Sekundär-Mint, Trend-Labels |
| `--ds-color-mint-glow` | `rgba(66,217,139,0.08)` | Active Tabs, Highlight-Flächen |
| `--ds-color-positive` | `#42d98b` | PnL positiv, LONG-Badge |
| `--ds-color-negative` | `#f05252` | PnL negativ, SHORT, Stop-Button |
| `--ds-color-warning` | `#d9a72e` | Pause-Button, Gauge-Mitte |

---

## Typografie

**Sans:** Inter (`--ds-font-sans`)  
**Mono:** JetBrains Mono (`--ds-font-mono`) — KPIs, Tabellenzahlen, Inputs

| Stufe | Größe | Verwendung |
|---|---|---|
| Hero | 26px | Sidebar-Titel „Hyperliquid Trading Bot“ |
| KPI | 24px | Kennzahlen-Werte (`font-mono`) |
| Body | 13px | Fließtext, Navigation, Panel-Titel |
| Table | 12px | Tabellenzeilen |
| Label | 11px | KPI-Labels, Footer, Chart-Achsen, Inputs |
| Table Header | 11px | Tabellenköpfe (uppercase) |
| Badge | 10px | LONG/SHORT-Badges |
| Micro | 9px | Architektur-Diagramm-Knoten |

**Line-height:** Body `leading-normal` (1.5), Tabellen `leading-tight`, KPIs `leading-none`

---

## Spacing-Skala

### Shell (primär ≥ 1921px CSS-Breite)

| Token | Wert |
|---|---|
| Shell padding top | 14px |
| Shell padding horizontal | 18px |
| Shell padding bottom | 18px |
| Main grid gap | 16px |
| Header gap (Navbar → Main) | 14px |
| Footer gap | 14px |
| Block gap (Dashboard-Sections) | 14px |
| Grid gap (KPI/Chart/Tables/Controls) | 12px |

### Card Padding (Komponente `Card`)

| Stufe | Tailwind | px |
|---|---|---|
| `xs` | `p-2.5` | 10px |
| `sm` | `p-3` | 12px |
| `md` | `p-3.5` | 14px |
| `lg` | `p-4` | 16px |

### Komponenten-Höhen (responsive)

| Komponente | ≥ 1921px | ≤ 1920px | ≤ 1706px |
|---|---|---|---|
| KPI-Karten | 100px | 94px | 90px |
| Performance-Chart | 380px | 320px | 280px |
| Steuerungspanels | 220px min | 200px min | 190px min |
| Navbar | 48px | 48px | 48px |

---

## Border-Radien

| Token | Wert | Verwendung |
|---|---|---|
| `--ds-radius-card` | 10px | `.card-surface`, Hauptkarten |
| `--ds-radius-panel` | 8px | `.panel-surface`, Sidebar-Icon-Boxen |
| `--ds-radius-button` | 6px | Bot-Buttons, Select |
| `--ds-radius-input` | 6px | Select-Felder |
| `--ds-radius-badge` | 4px | Badges, PnL-Pills, Number-Input |
| `--ds-radius-icon` | 6px | Konzept-Layer-Icons |

---

## Panel-Stile

### Card Surface (`.card-surface`)

```css
border-radius: var(--ds-radius-card);
border: 1px solid var(--ds-color-border);
background: var(--ds-color-bg-card);
box-shadow: inset 0 1px 0 var(--ds-color-card-inset),
            0 1px 2px var(--ds-color-card-shadow);
```

### Panel Surface (`.panel-surface`)

```css
border-radius: var(--ds-radius-panel);
border: 1px solid var(--ds-color-border-subtle);
background: var(--ds-color-bg-panel);
```

### Panel Header (`PanelHeader`)

- Titel: 13px, `font-medium`, `text-text-primary`
- Subtitle: 11px, `text-text-muted`
- Compact margin-bottom: 8px (`mb-2`)

### Control Panel (`.control-panel`)

- Min-height via `--controls-height`
- Inhalt: `flex-1 justify-between` für gleichmäßige Verteilung
- Padding: `sm` (12px)

---

## Tabellen-Stile

| Element | Stil |
|---|---|
| Header | 11px, uppercase, `tracking-[0.04em]`, `text-text-muted` |
| Zeilen | 12px, `leading-tight`, `py-1`, `pr-0.5` |
| Zahlen | `font-mono`, 11px, `text-text-secondary` / `text-text-muted` |
| Trennlinien | `divide-border-subtle/80` |
| Hover | `hover:bg-white/[0.015]` |
| PnL | `PnlPill` — 11px mono, mint/red Hintergrund |

Tabellen-Grid: `minmax(0, 1.6fr) minmax(0, 1fr)` — Positionen breiter als Trades.

---

## Button-Varianten

| Variante | Klassen | Verwendung |
|---|---|---|
| **Primary** | `bg-mint text-bg-base rounded-[6px] py-1.5 text-[12px]` | Bot starten |
| **Warning outline** | `border border-warning/40 text-warning hover:bg-warning/5` | Bot pausieren |
| **Danger outline** | `border border-negative/40 text-negative hover:bg-negative/5` | Bot stoppen |
| **Nav link** | 13px, inactive `text-text-secondary`, active `.nav-active` + Mint-Unterstrich | Navbar |
| **Chart period** | 11px, active: `border-mint/20 bg-mint-glow text-mint` | Performance-Tabs |
| **Toggle** | 36×20px Track, 16px Thumb, mint when enabled | Bot/Risiko/Filter |

---

## Statusfarben & Badges

| Status | Badge-Variant | Farbe |
|---|---|---|
| LONG | `positive` | Mint auf `bg-mint/10` |
| SHORT | `negative` | Rot auf `bg-red-500/10` |
| Bot AKTIV | — | `text-mint` 24px |
| PnL + | `PnlPill` | `bg-mint/12 text-positive` |
| PnL − | `PnlPill` | `bg-negative/10 text-negative` |
| R-Multiple + | — | `text-mint-dim` |
| R-Multiple − | — | `text-negative` |

---

## Layout-Grid (eingefroren)

```
dashboard-shell (100% width, no max-width)
└── main-grid
    ├── aside: clamp(340px, 19vw, 420px)
    └── main-column
        ├── Navbar (h-12)
        ├── dashboard-content
        │   ├── kpi-grid (6 columns)
        │   ├── chart-grid (4fr + clamp(230px, 18vw, 310px))
        │   ├── tables-grid (1.6fr + 1fr)
        │   └── controls-grid (4 columns)
        └── Footer
```

Alle Grid-Kinder: `min-width: 0` (Overflow-Schutz).

---

## Responsive Breakpoints

Breakpoints basieren auf **CSS-Viewport-Pixeln** (beeinflusst durch Windows-Anzeigeskalierung).

| Name | Media Query | Typischer Kontext | Viewport-Test |
|---|---|---|---|
| **Primary (WQHD)** | default (> 1920px) | WQHD @ 125% → ~2048×1152 | 2048×1152 |
| **Secondary (FHD)** | `max-width: 1920px` | Full HD | 1920×1080 |
| **Compact** | `max-width: 1706px` | WQHD @ 150% → ~1707×960 | 1707×960 |

Referenz-Screenshots: `docs/visual-regression/dashboard-{viewport}.png`

---

## Chart (Performance)

- Display-only Mockdaten in `PerformanceChart.tsx` (`CHART_DISPLAY_DATA`)
- Linie: `#42d98b`, 1.75px, `monotone`
- Fläche: Gradient 22% → 0% Opacity
- Achsen: 11px, `#6d7a84`
- SSR: Chart via `dynamic(..., { ssr: false })` — Hydration-sicher

---

## Visuelle Regression

```bash
npm run build
npm run test:visual
```

Screenshots werden in `docs/visual-regression/` gespeichert.  
Aktuell **keine** strikte Pixel-Toleranz — Referenzstand für manuelle Diff-Prüfung.

---

## Changelog

| Version | Datum | Änderung |
|---|---|---|
| 1.0.0 | 2026-07-11 | Design-Freeze, initiale Dokumentation |
