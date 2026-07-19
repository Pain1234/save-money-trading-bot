# SAVE-MONEY BOT — Risk Specification V1

**Version:** 1.0.0 (Specification Freeze)  
**Status:** Verbindlich, implementierbar  
**Referenzen:** [product-specification.md](./product-specification.md), [strategy-specification.md](./strategy-specification.md)

---

## 1. Risiko-Philosophie (V1)

Das Risiko-Modell trennt strikt:

1. **Trade-Risiko** — maximaler Verlust eines Trades bis `EffectiveStop`
2. **Portfolio-Risiko** — Summe aller offenen Trade-Risiken (`Current Open Risk`)
3. **Hebel-Limit** — Obergrenze der Notional-Exposure (**Margin-Effizienz**, kein Risiko-Boost)

**Verbindliche Regel Hebel:** Positionsgröße wird **ausschließlich** aus `risk_per_trade_pct` und `StopDistance` abgeleitet. Hebel darf das zulässige Kontorisiko **niemals erhöhen**. Er begrenzt nur die maximale Notional-Exposure; bei Konflikt wird die Positionsgröße **reduziert** oder der Entry **abgelehnt** — nie erhöht.

Alle Limits sind **Hard Limits** — Verletzung → `RC_REJECT_*`, keine stille Anpassung nach oben.

---

## 2. Definitionen

| Begriff | Formel / Bedeutung |
|---|---|
| **Equity** | `AccountBalance + UnrealizedPnL` (USD, Mark-to-Market) |
| **EntryPrice** | Durchschnittlicher Fill-Preis |
| **StopInitial** | `EntryPrice − stop_initial_atr_mult × ATR14` (Strategy Spec §6) |
| **TrailStop** | Trailing Stop (Strategy Spec §7) |
| **EffectiveStop** | `max(StopInitial, TrailStop)` |
| **StopDistance** | `EntryPrice − StopInitial` (USD pro Base-Einheit) |
| **PositionSize** | Menge in Base Asset (BTC/ETH/SOL), gerundet |
| **Notional** | `PositionSize × MarkPrice` |
| **RiskBudgetUSD (Trade)** | `Equity × risk_per_trade_pct / 100` |
| **ActualRiskUSD (Trade)** | `PositionSize × (EntryPrice − EffectiveStop)` nach Rundung |
| **Current Open Risk** | Siehe §4.2 |
| **Projected Portfolio Risk** | Siehe §4.3 |

### 2.1 Exchange-Rundung

Pro Symbol von Hyperliquid geladen:

| Feld | Funktion |
|---|---|
| `tick_size` | `round_to_tick(price, tick_size)` für Stops |
| `quantity_step` | `floor_to_step(qty, quantity_step)` für Positionsgröße |
| `min_order_size` | Mindest-Ordermenge |

```
floor_to_step(x, step) = floor(x / step) × step
round_to_tick(price, tick) = floor(price / tick) × tick   // Long-Stop: floor
```

---

## 3. Risiko pro Trade

### 3.1 Limit

```
risk_per_trade_pct = 0.5
RISK_PER_TRADE = risk_per_trade_pct / 100 = 0.005
```

### 3.2 Positionsgrößenberechnung (Long)

Gegeben: `Equity`, `EntryPrice`, `ATR14` (Entry-Tag, letzte geschlossene Kerze):

```
StopInitial = EntryPrice − (stop_initial_atr_mult × ATR14)
StopInitial = round_to_tick(StopInitial, tick_size)
StopDistance = EntryPrice − StopInitial

Falls StopDistance <= 0:
  → REJECT RC_REJECT_DATA

RiskBudgetUSD = Equity × RISK_PER_TRADE
PositionSize_raw = RiskBudgetUSD / StopDistance
PositionSize = floor_to_step(PositionSize_raw, quantity_step)
```

### 3.3 Mindestgröße

```
Falls PositionSize < min_order_size:
  → REJECT RC_REJECT_RISK_TRADE
```

### 3.4 Validierung nach Rundung (Pflicht)

Nach `floor_to_step` **muss** das tatsächliche Risiko erneut geprüft werden:

```
ActualRiskUSD = PositionSize × StopDistance
ActualRiskPct = (ActualRiskUSD / Equity) × 100

Falls ActualRiskPct > risk_per_trade_pct × (1 + risk_rounding_tolerance):
  PositionSize := floor_to_step(PositionSize − quantity_step, quantity_step)
  Neuberechnung ActualRiskUSD / ActualRiskPct
  Wiederholen bis OK oder PositionSize < min_order_size → REJECT RC_REJECT_RISK_TRADE

Ziel: ActualRiskPct ≤ risk_per_trade_pct
```

`risk_rounding_tolerance = 0.001` (0,1 % relative Toleranz auf das Limit).

**Wichtig:** Rundung darf Risiko nur **senken**, nie erhöhen über das Limit hinaus.

---

## 4. Portfoliorisiko

### 4.1 Limit

```
max_portfolio_risk_pct = 2.0
MAX_PORTFOLIO_RISK = max_portfolio_risk_pct / 100 = 0.02
```

### 4.2 Current Open Risk (mathematisch eindeutig)

Für jede offene Position `i`:

```
EffectiveStop_i = max(StopInitial_i, TrailStop_i)
OpenRiskUSD_i = PositionSize_i × max(0, EntryPrice_i − EffectiveStop_i)
```

```
CurrentOpenRiskUSD = Σ OpenRiskUSD_i    // über alle offenen Positionen
current_open_risk_pct = (CurrentOpenRiskUSD / Equity) × 100
```

Trailing Stop reduziert `OpenRiskUSD_i` (Stop steigt → Distanz zu Entry sinkt). Clamp auf 0 verhindert negatives Risiko.

### 4.3 Projected Portfolio Risk (Pre-Entry)

Für einen **neuen** Kandidaten-Trade mit berechnetem `RiskBudgetUSD_new` (aus §3.2, **vor** Portfolio-Freigabe):

```
ProjectedPortfolioRiskUSD = CurrentOpenRiskUSD + RiskBudgetUSD_new
projected_portfolio_risk_pct = (ProjectedPortfolioRiskUSD / Equity) × 100
```

**Hinweis:** Für den Pre-Entry-Check wird `RiskBudgetUSD_new = Equity × RISK_PER_TRADE` verwendet (Zielbudget). Nach Rundung wird `ActualRiskUSD_new` für Audit geloggt; der Entry ist nur erlaubt, wenn:

```
projected_portfolio_risk_pct ≤ max_portfolio_risk_pct
```

Alternativ equivalent mit tatsächlichem Risiko nach Rundung:

```
ProjectedPortfolioRiskUSD_actual = CurrentOpenRiskUSD + ActualRiskUSD_new
projected_portfolio_risk_pct_actual = (ProjectedPortfolioRiskUSD_actual / Equity) × 100

Falls projected_portfolio_risk_pct_actual > max_portfolio_risk_pct:
  → REJECT RC_REJECT_RISK_PORTFOLIO
```

Beide Prüfungen sollten konsistent sein; die **actual**-Variante ist nach Rundung verbindlich.

### 4.4 Pre-Entry Check (Reihenfolge)

```
1. Warmup, Daten, Strategie-Signal OK
2. count(open_positions) < max_open_positions
3. Keine offene Position auf Symbol
4. Trade-Risiko nach Rundung ≤ risk_per_trade_pct
5. projected_portfolio_risk_pct_actual ≤ max_portfolio_risk_pct
6. Hebel-Check §6 (nur Reduktion, kein Risiko-Boost)
```

---

## 5. Maximale Anzahl Positionen

```
max_open_positions = 3
```

- Maximal **eine** Position pro Symbol.
- Maximal **drei** Positionen gesamt.

```
Falls count(open_positions) >= max_open_positions:
  → REJECT RC_REJECT_MAX_POSITIONS

Falls open_position(symbol):
  → REJECT RC_REJECT_DUPLICATE_SYMBOL
```

---

## 6. Hebel-Limit

```
max_leverage = 2.0
```

### 6.1 Berechnung

```
TotalNotional = Σ (PositionSize_i × MarkPrice_i)
ProjectedNotional = TotalNotional + (PositionSize_new × EntryPrice_new)
projected_leverage = ProjectedNotional / Equity
```

### 6.2 Pre-Entry Check (Hebel reduziert nur, erhöht nie)

Hebel ist **kein Sizing-Ziel**. Ablauf:

```
1. PositionSize aus §3 (risikobasiert) berechnen
2. projected_leverage prüfen

Falls projected_leverage <= max_leverage:
  → Hebel OK

Falls projected_leverage > max_leverage:
  MaxNewNotional = max_leverage × Equity − TotalNotional
  PositionSize_capped = floor_to_step(MaxNewNotional / EntryPrice, quantity_step)
  PositionSize := min(PositionSize, PositionSize_capped)    // NUR Reduktion

3. ActualRiskPct und projected_portfolio_risk_pct_actual neu berechnen (§3.4, §4.3)

Falls PositionSize < min_order_size
   OR ActualRiskPct > risk_per_trade_pct (unwahrscheinlich nach Reduktion)
   OR projected_portfolio_risk_pct_actual > max_portfolio_risk_pct:
  → REJECT RC_REJECT_LEVERAGE
```

**Verboten:** Positionsgröße über risikobasiertem Wert anheben, um Hebel auszunutzen.

---

## 7. Stop- & Exit-Risiko (Execution)

### 7.1 Initial Stop Order

| Feld | Wert |
|---|---|
| Typ | Stop-Market (Sell) |
| Trigger | `StopInitial` (tick-gerundet) |
| Menge | `PositionSize` |
| TIF | GTC |

Platzierung unmittelbar nach Entry-Fill.

### 7.2 Trailing Stop Update

Täglich nach Daily Close (Strategy Spec §7.3): cancel-replace wenn `EffectiveStop` steigt. Nie senken.

### 7.3 Gap- und Stop-Ausführung

Strategy Spec §8.1 (verbindlich):

```
Falls Open[t] < EffectiveStop:
  ExitPrice = Open[t]          // RC_EXIT_STOP_GAP
Sonst falls Low[t] <= EffectiveStop:
  ExitPrice = EffectiveStop    // RC_EXIT_STOP_INITIAL / RC_EXIT_STOP_TRAILING
```

PnL-Berechnung: `(ExitPrice − EntryPrice) × PositionSize`.

### 7.4 Slippage (Backtest only)

| Szenario | Parameter |
|---|---|
| Stop-Market (non-gap) | Stop ± 0,1 % |
| Gap-Exit | Open (exakt) |
| Entry Market | Close ± 0,05 % |

---

## 8. Fear & Greed

```
FEAR_GREED_AFFECTS_RISK = false
```

Keine Anpassung von Size, Stops oder Entry-Freigabe.

---

## 9. Fehlerfälle

| Situation | Reaktion |
|---|---|
| Equity ≤ 0 | `ERROR`, Entries blockiert |
| Equity nicht abrufbar | `DEGRADED` |
| StopDistance ≤ 0 | `RC_REJECT_DATA` |
| PositionSize nach Rundung = 0 | `RC_REJECT_RISK_TRADE` |
| Stop-Order fehlgeschlagen | `ERROR` |
| Partial Fill | Size/Stop/Risiko neu berechnen |
| Reconciliation mismatch | `ERROR`, Freeze Entries |

---

## 10. Worked Example (Portfolio)

**Equity:** 100.000 USD  
**Offene Positionen:** BTC (`OpenRiskUSD = 480`), ETH (`OpenRiskUSD = 510`)

```
CurrentOpenRiskUSD = 480 + 510 = 990
current_open_risk_pct = 0.99 %
```

**Neuer SOL-Entry:** `RiskBudgetUSD = 500`, nach Rundung `ActualRiskUSD = 495`

```
ProjectedPortfolioRiskUSD_actual = 990 + 495 = 1.485
projected_portfolio_risk_pct_actual = 1.485 % ≤ 2.0 %  ✓
```

---

## 11. Worked Example (Rundung)

**Equity:** 100.000, **EntryPrice:** 95.000, **ATR14:** 2.400, **quantity_step:** 0.001

```
StopDistance = 6.000
PositionSize_raw = 500 / 6.000 = 0.08333…
PositionSize = floor_to_step(0.08333, 0.001) = 0.083
ActualRiskUSD = 0.083 × 6.000 = 498 USD → 0.498 % ≤ 0.5 %  ✓
```

---

## 12. Reason Codes (Risk)

| Code | Bedingung |
|---|---|
| `RC_REJECT_RISK_TRADE` | ActualRiskPct > risk_per_trade_pct nach Rundung |
| `RC_REJECT_RISK_PORTFOLIO` | projected_portfolio_risk_pct_actual > max_portfolio_risk_pct |
| `RC_REJECT_MAX_POSITIONS` | ≥ max_open_positions |
| `RC_REJECT_DUPLICATE_SYMBOL` | Symbol bereits offen |
| `RC_REJECT_LEVERAGE` | Hebel > max_leverage nach Reduktion / min_size |
| `RC_RISK_APPROVED` | Alle Checks bestanden |

Vollständige Liste: Strategy Spec §10.

---

## 13. Abnahmekriterien (Risk V1)

- [ ] `floor_to_step` mit `quantity_step`
- [ ] Stops mit `tick_size`
- [ ] Risiko-Nachtest nach Rundung (§3.4)
- [ ] `CurrentOpenRiskUSD` mit `EffectiveStop`
- [ ] `ProjectedPortfolioRiskUSD_actual` Pre-Entry
- [ ] Hebel reduziert Size, erhöht nie Risiko
- [ ] Gap-Exit zu Open

---

## 14. Schnittstelle Strategy ↔ Risk

```
interface RiskCheckRequest {
  symbol: string
  entry_price: number
  atr14: number
  equity: number
  tick_size: number
  quantity_step: number
  min_order_size: number
  open_positions: OpenPosition[]
}

interface OpenPosition {
  symbol: string
  entry_price: number
  position_size: number
  stop_initial: number
  trail_stop: number
}

interface RiskCheckResult {
  approved: boolean
  reason_code: string
  position_size?: number
  stop_initial?: number
  actual_risk_usd?: number
  actual_risk_pct?: number
  current_open_risk_pct?: number
  projected_portfolio_risk_pct?: number
  projected_leverage?: number
}
```

---

## Specification Freeze – Version 1.0

Verbindliche Standardparameter (Baseline). Siehe auch Product Spec §Specification Freeze.

| Parameter | Symbol | Standardwert |
|---|---|---|
| Symbole | `SYMBOLS` | BTC, ETH, SOL |
| Risiko pro Trade | `risk_per_trade_pct` | 0.5 % |
| Max. Portfoliorisiko | `max_portfolio_risk_pct` | 2.0 % |
| Max. Positionen | `max_open_positions` | 3 |
| Max. Hebel | `max_leverage` | 2.0 (Margin only) |
| Initial Stop ATR-Mult | `stop_initial_atr_mult` | 2.5 |
| Trailing Stop ATR-Mult | `trail_atr_mult` | 3.0 |
| Volume Ratio Minimum | `volume_ratio_min` | 1.00 (Backtest: 1.20) |
| Pullback EMA Toleranz | `pullback_ema_tolerance` | 0.005 |
| Risiko-Rundungstoleranz | `risk_rounding_tolerance` | 0.001 |
| Monthly / Weekly / Daily EMA | `MONTHLY_EMA_PERIOD` etc. | 20 / 20+50 / 20 |
| ATR / Volume SMA | `ATR_PERIOD` / `VOLUME_SMA_PERIOD` | 14 / 20 |
| Breakout Lookback | `BREAKOUT_LOOKBACK` | 20 |
| Warmup | — | Daily ≥ 21, Weekly ≥ 50, Monthly ≥ 20 |
| Weekly-Trend Auto-Exit | — | deaktiviert |
| Fear & Greed | — | deaktiviert |

---

## Changelog

| Version | Datum | Änderung |
|---|---|---|
| 1.0.0 | 2026-07-11 | Specification Freeze — Review & Klarstellungen |
