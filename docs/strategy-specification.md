# SAVE-MONEY BOT — Strategy Specification V1

**Version:** 1.0.0 (Specification Freeze)  
**Status:** Verbindlich, implementierbar  
**Richtung:** Long-only  
**Symbole:** BTC, ETH, SOL  
**Referenzen:** [product-specification.md](./product-specification.md), [risk-specification.md](./risk-specification.md)

---

## 1. Strategie-Übersicht

Strategy V1 ist ein **regime-gefilterter Trendfolge-Ansatz** mit zwei Daily-Entry-Modellen. Alle Filter müssen erfüllt sein (logisches AND), außer wo explizit OR vermerkt.

```
Monthly Regime (Close > EMA20)
        AND
Weekly Trend (EMA20 > EMA50)
        AND
Daily Entry (Breakout OR Pullback)
        AND
Volume Ratio ≥ volume_ratio_min
        AND
Risk Engine OK
        → LONG Entry (max. 1 Orderabsicht / Symbol / Daily Close)
```

---

## 2. Zeitrahmen & UTC-Regeln

### 2.1 Kerzen-Definitionen (UTC)

| Timeframe | `open_time` | `close_time` (inklusiv) |
|---|---|---|
| **1D** | `YYYY-MM-DD 00:00:00 UTC` | `YYYY-MM-DD 23:59:59 UTC` |
| **1W** | Montag `00:00:00 UTC` | Sonntag `23:59:59 UTC` |
| **1M** | `YYYY-MM-01 00:00:00 UTC` | Letzter Tag `23:59:59 UTC` |

### 2.2 Abgeschlossene Kerzen (Closed Candle Rule)

Kerze `C` mit `close_time = T_close` ist **geschlossen**, wenn:

```
now_utc >= T_close
```

**Implementierungsregel:**

- Signale werden am **Daily-Close-Event** ausgewertet (`now_utc >= daily_close_time(t)`).
- Weekly/Monthly: letzte Kerze mit `close_time <= now_utc` (größtes `open_time`).
- Die **laufende** Kerze wird **niemals** in Indikator- oder Signalberechnungen einbezogen.

### 2.3 Auswertungs-Zeitplan (V1)

| Event | UTC-Zeitpunkt | Aktion |
|---|---|---|
| Daily Close | `00:00:05 UTC` | Indikatoren, Entry/Exit, Trailing-Update |
| Weekly Close | Montag `00:00:10 UTC` | Weekly-EMAs aktualisieren |
| Monthly Close | 1. des Monats `00:00:15 UTC` | Monthly-Regime, Regime-Exits |

---

## 3. Benötigte Historie (Warmup)

### 3.1 Mindestanforderungen pro Symbol (Hard Block)

Warmup endet erst, wenn **alle** Zeilen erfüllt sind:

| Indikator | Timeframe | Mindest geschlossene Kerzen | Formel / Begründung |
|---|---|---|---|
| EMA20 | Monthly | **20** | SMA-Seed + EMA(20) |
| EMA20 | Weekly | **20** | SMA-Seed + EMA(20) |
| EMA50 | Weekly | **50** | SMA-Seed + EMA(50) |
| EMA20 | Daily | **20** | SMA-Seed + EMA(20) |
| ATR14 | Daily | **15** | 14 TR-Werte + `C[t−1]` für TR |
| Vol SMA20 | Daily | **20** | `Σ V[t−19..t] / 20` |
| High20 | Daily | **21** | Kerzen `t−1 … t−20` benötigt (Breakout ab Tag 21) |

**Globaler Daily-Mindestwert:** `max(20, 15, 20, 21) = 21` geschlossene Daily-Kerzen.  
**Globaler Weekly-Mindestwert:** **50** geschlossene Weekly-Kerzen.  
**Globaler Monthly-Mindestwert:** **20** geschlossene Monthly-Kerzen.

```
WARMUP_complete(symbol) =
  daily_count  >= 21
  AND weekly_count  >= 50
  AND monthly_count >= 20
```

Bot-Status: `WARMUP` bis für **jedes** Symbol `WARMUP_complete = true`.

### 3.2 Empfohlene Historie (Produktion)

| Timeframe | Kerzen | ~Zeitraum |
|---|---|---|
| Daily | 400 | ~13 Monate |
| Weekly | 100 | ~2 Jahre |
| Monthly | 36 | ~3 Jahre |

---

## 4. Indikator-Formeln

Notation: `C[t]`, `H[t]`, `L[t]`, `V[t]` = OHLCV der Kerze `t` (letzte **geschlossene** Kerze zum Evaluierungszeitpunkt).

### 4.1 EMA

```
α(n) = 2 / (n + 1)
EMA_n[0] = SMA_n der ersten n Closes
EMA_n[t] = α(n) × C[t] + (1 − α(n)) × EMA_n[t−1]
```

Gilt für: Monthly EMA20, Weekly EMA20/50, Daily EMA20.

### 4.2 ATR14 — Wilder (Daily)

```
TR[t] = max(
  H[t] − L[t],
  |H[t] − C[t−1]|,
  |L[t] − C[t−1]|
)

ATR[0] = SMA(TR, 14) über Kerzen 1..14
ATR[t] = (ATR[t−1] × 13 + TR[t]) / 14
```

Ergebnis: `ATR14_daily[t]` in Preiseinheiten des Symbols.

### 4.3 Volume Ratio (Daily)

```
VolSMA20[t] = (1 / VOLUME_SMA_PERIOD) × Σ(i=t−19..t) V[i]

VolumeRatio[t] = V[t] / VolSMA20[t]
```

Falls `VolSMA20[t] = 0` oder undefined → kein Entry (`RC_REJECT_DATA`).

### 4.4 20-Tage-Hoch (Breakout)

```
High20[t] = max(H[t−1], H[t−2], …, H[t−BREAKOUT_LOOKBACK])
          = max(H[t−k]) für k ∈ {1, 2, …, 20}
```

**Verbindlich:** Kerze `t` (aktuelle abgeschlossene Daily-Kerze) ist **nicht** in `High20[t]` enthalten. Nur die **20 vorherigen abgeschlossenen** Kerzen.

Falls weniger als 20 Prior-Kerzen vorhanden: `High20[t]` undefined → kein Breakout-Entry.

---

## 5. Filter & Entry-Bedingungen

### 5.1 Monthly Regime

```
RegimeLong[t] = C_month[t] > EMA20_month[t]
```

`false` → kein neuer Entry. Bestehende Positionen: Exit §8.3.

### 5.2 Weekly Trend-Bestätigung

```
TrendConfirmed[t] = EMA20_week[t] > EMA50_week[t]
```

`false` → kein Entry. **Kein automatischer Exit** bei Trendbruch in V1 (§8.4).

### 5.3 Volume Ratio Filter

```
VolumeOK[t] = VolumeRatio[t] >= volume_ratio_min
```

| Parameter | Typ | Baseline-Standard | Backtest-Variante |
|---|---|---|---|
| `volume_ratio_min` | konfigurierbar | **1.00** | **1.20** (separater Backtest-Lauf) |

Reject bei `VolumeOK = false`: `RC_REJECT_VOLUME`.

### 5.4 Daily Entry — Modell A: 20-Tage-Breakout

```
BreakoutEntry[t] =
  C[t] > High20[t]
  AND C[t] > EMA20_daily[t]
  AND RegimeLong[t]
  AND TrendConfirmed[t]
  AND VolumeOK[t]
```

- **Entry-Preis (Signal):** `C[t]`
- **Reason Code:** `RC_ENTRY_BREAKOUT_20D`
- **entry_type:** `BREAKOUT`

### 5.5 Daily Entry — Modell B: Pullback an Daily EMA20

Pullback ist **objektiv** definiert über Low, Close und EMA20 der abgeschlossenen Kerze `t` sowie den Vortag `t−1`.

Parameter:

```
pullback_ema_tolerance = 0.005    // 0,5 %, konfigurierbar
EMA_touch_upper[t] = EMA20_daily[t] × (1 + pullback_ema_tolerance)
```

Bedingungen (alle AND):

```
P1: C[t] > EMA20_daily[t]                           // Close über EMA
P2: L[t] <= EMA_touch_upper[t]                      // Low berührt EMA (+ Toleranz)
P3: C[t−1] > EMA20_daily[t−1]                       // Vortag bereits über EMA
P4: RegimeLong[t]
P5: TrendConfirmed[t]
P6: VolumeOK[t]
```

```
PullbackEntry[t] = P1 AND P2 AND P3 AND P4 AND P5 AND P6
```

- **Reason Code:** `RC_ENTRY_PULLBACK_EMA20`
- **entry_type:** `PULLBACK`

**Nicht verwendet (subjektiv, V1 ausgeschlossen):** „Trend intakt“, „qualitativer Pullback“, Wick-Ratio, manuelle Chart-Einschätzung.

### 5.6 Entry-Priorität & Orderabsicht

Wenn `BreakoutEntry[t] = true` **und** `PullbackEntry[t] = true` (ohne `NOT Breakout` in Pullback):

1. Es wird **genau eine** Orderabsicht erzeugt.
2. `entry_type = BREAKOUT`
3. `reason_code = RC_ENTRY_BREAKOUT_20D`
4. **Keine** zweite Orderabsicht mit `entry_type = PULLBACK`.

Allgemein: maximal **eine** Orderabsicht pro Symbol pro Daily-Close-Event.

### 5.7 Kein Entry wenn

| Bedingung | Reason Code |
|---|---|
| Position auf Symbol offen | `RC_REJECT_DUPLICATE_SYMBOL` |
| Warmup aktiv | `RC_REJECT_WARMUP` |
| `RegimeLong = false` | `RC_REJECT_REGIME` |
| `TrendConfirmed = false` | `RC_REJECT_TREND` |
| `VolumeOK = false` | `RC_REJECT_VOLUME` |
| Risk Engine reject | Risk Spec §13 |

---

## 6. Initialer Stop (Entry)

Bei Entry an Daily Close `t`:

```
StopInitial = EntryPrice − (stop_initial_atr_mult × ATR14_daily[t])
StopInitial = round_to_tick(StopInitial, tick_size)
```

- `stop_initial_atr_mult = 2.5` (Baseline)
- `EntryPrice` = Fill-Preis (Execution); Signal-Preview: `C[t]`
- Stop-Typ: Stop-Market (Long: Auslösung wenn Preis ≤ Stop)

**Reason Code:** `RC_EXIT_STOP_INITIAL`

---

## 7. Trailing Stop

Trailing Stop nutzt **ATR14 der letzten abgeschlossenen Daily-Kerze** (`ATR14_daily[t]`). Der Stop-Preis darf **ausschließlich steigen** (Ratchet up only).

### 7.1 Zustandsvariablen (pro Position)

| Variable | Bedeutung |
|---|---|
| `HighestClose` | Höchster Daily-Close seit Entry |
| `TrailStop` | Aktueller Trailing-Stop-Preis |
| `StopInitial` | Initialer Stop (unverändert bis Exit) |

### 7.2 Initialisierung (Entry-Tag `t₀`)

```
HighestClose := EntryPrice
ATR_entry := ATR14_daily[t₀]          // letzte abgeschlossene Kerze am Entry
TrailStop := HighestClose − (trail_atr_mult × ATR_entry)
TrailStop := max(TrailStop, StopInitial)
TrailStop := round_to_tick(TrailStop, tick_size)
```

`trail_atr_mult = 3.0` (Baseline).

### 7.3 Daily-Update-Reihenfolge (exakt, nach jedem Daily Close `t`)

Schritte **in dieser Reihenfolge** ausführen:

```
1. atr_current  := ATR14_daily[t]              // ATR der gerade geschlossenen Kerze t
2. HighestClose := max(HighestClose, C[t])
3. trail_candidate := HighestClose − (trail_atr_mult × atr_current)
4. TrailStop    := max(TrailStop, trail_candidate)   // nur steigen, nie sinken
5. TrailStop    := max(TrailStop, StopInitial)       // nie unter Initial-Stop
6. TrailStop    := round_to_tick(TrailStop, tick_size)
7. EffectiveStop := max(StopInitial, TrailStop)
8. Stop-Order cancel-replace wenn EffectiveStop > bisheriger Stop-Order-Preis
```

### 7.4 Effective Stop

```
EffectiveStop = max(StopInitial, TrailStop)
```

Exit-Trigger (Stop): siehe §8.1 und §8.5 (Gap-Regel).

**Reason Code (Trailing):** `RC_EXIT_STOP_TRAILING`  
**Reason Code (Gap durch Stop):** `RC_EXIT_STOP_GAP`

---

## 8. Exit-Bedingungen (vollständig)

| # | Bedingung | Reason Code |
|---|---|---|
| 1 | Stop Initial (2,5 × ATR) | `RC_EXIT_STOP_INITIAL` |
| 2 | Stop Trailing (3 × ATR) | `RC_EXIT_STOP_TRAILING` |
| 3 | Gap-Stop (Open unter Stop) | `RC_EXIT_STOP_GAP` |
| 4 | Monthly Regime fällt | `RC_EXIT_REGIME_MONTHLY` |
| 5 | Manueller Exit | `RC_EXIT_MANUAL` |

### 8.1 Stop-Auslösung (Intraday / Daily)

An jedem Tag `t` mit offener Position, **vor** oder **während** der Kerze:

```
EffectiveStop = max(StopInitial, TrailStop)    // Stand nach letztem Daily-Update
```

**Gap- und Stop-Ausführung (verbindlich):**

```
Falls Open[t] < EffectiveStop:
  ExitPrice := Open[t]
  reason_code := RC_EXIT_STOP_GAP
Sonst falls Low[t] <= EffectiveStop:
  ExitPrice := EffectiveStop
  reason_code := RC_EXIT_STOP_INITIAL oder RC_EXIT_STOP_TRAILING
    (je nachdem welcher Stop ausgelöst hat; bei Gleichstand Trailing bevorzugt wenn TrailStop >= StopInitial)
Sonst:
  Kein Stop-Exit an Tag t
```

`ExitPrice` wird auf `tick_size` gerundet (Richtung für Long-Exit: floor).

### 8.2 Regime-Exit (Monthly)

- Auswertung: Monthly-Close-Event (1. des Monats, 00:00:15 UTC).
- Wenn `RegimeLong = false` und Position offen:
  - Exit-Signal generieren (`RC_EXIT_REGIME_MONTHLY`).
  - Ausführung: Market Close beim **nächsten Daily-Close-Event** (`00:00:05 UTC`).

### 8.3 Kein Exit bei

- Volume Ratio fällt unter `volume_ratio_min`
- Pullback-Bedingung nicht mehr erfüllt
- Breakout-Level nicht mehr gültig

### 8.4 Weekly-Trendbruch (eindeutig V1)

```
WeeklyTrendBroken[t] = EMA20_week[t] <= EMA50_week[t]
```

| Aspekt | V1-Verhalten |
|---|---|
| Neuer Entry | **Blockiert** (`RC_REJECT_TREND`) |
| Offene Position schließen | **Nein** — kein Auto-Exit |
| Stop-Updates | **Fortgesetzt** (Trailing/Initial unverändert) |
| Re-Entry nach Recovery | Erlaubt, wenn alle Entry-Bedingungen erneut erfüllt |

**Begründung V1:** Weekly-Filter dient ausschließlich der Entry-Qualität, nicht der Exit-Logik.

---

## 9. Positionsgröße (Referenz)

Detail: [risk-specification.md](./risk-specification.md).

---

## 10. Reason Codes (vollständig)

### 10.1 Entry

| Code | Beschreibung |
|---|---|
| `RC_ENTRY_BREAKOUT_20D` | 20-Tage-Breakout |
| `RC_ENTRY_PULLBACK_EMA20` | Pullback Daily EMA20 |

### 10.2 Exit

| Code | Beschreibung |
|---|---|
| `RC_EXIT_STOP_INITIAL` | Initialer Stop (2,5 × ATR) |
| `RC_EXIT_STOP_TRAILING` | Trailing Stop (3 × ATR) |
| `RC_EXIT_STOP_GAP` | Gap unter Stop — Exit zu Open |
| `RC_EXIT_REGIME_MONTHLY` | Monthly Regime Exit |
| `RC_EXIT_MANUAL` | Manueller Exit |

### 10.3 Reject

| Code | Beschreibung |
|---|---|
| `RC_REJECT_REGIME` | Monthly Regime nicht long |
| `RC_REJECT_TREND` | Weekly Trend nicht bestätigt |
| `RC_REJECT_VOLUME` | Volume Ratio < volume_ratio_min |
| `RC_REJECT_WARMUP` | Warmup aktiv |
| `RC_REJECT_DATA` | Fehlende/ungültige Daten |
| `RC_REJECT_DUPLICATE_SYMBOL` | Position existiert |
| `RC_REJECT_RISK_TRADE` | Trade-Risiko > risk_per_trade_pct |
| `RC_REJECT_RISK_PORTFOLIO` | projected_portfolio_risk_pct > max_portfolio_risk_pct |
| `RC_REJECT_MAX_POSITIONS` | ≥ max_open_positions |
| `RC_REJECT_LEVERAGE` | Hebel > max_leverage nach Anpassung |
| `RC_REJECT_NO_SIGNAL` | Kein Entry-Signal (Debug) |
| `RC_RISK_APPROVED` | Risk-Checks bestanden (Audit) |

---

## 11. Fehlerfälle & ungültige Daten

| Situation | Verhalten |
|---|---|
| `ATR14 = 0` oder undefined | Kein Entry; `RC_REJECT_DATA` |
| `EMA20 = NaN` | `WARMUP` |
| Fehlende Daily-Kerze | Kein Entry; `DATA_GAP` |
| `High20` undefined | Kein Breakout-Entry |
| `StopDistance <= 0` | `RC_REJECT_DATA` |

---

## 12. Look-ahead-Bias-Schutz

| Regel | Implementierung |
|---|---|
| L1 | Index `t` = letzte geschlossene Kerze |
| L2 | `High20[t]` nur aus `t−1 … t−20`, **nicht** `t` |
| L3 | Pullback nutzt `C[t−1]`, `EMA20[t−1]` |
| L4 | Weekly/Monthly aus letzter geschlossener höherer TF-Kerze |
| L5 | Backtest: Signale ab `close_time + 1ms` |
| L6 | Kein `shift(-1)` / zukünftige Closes |

### Abnahme-Test

```
Given: Breakout an Tag t, High20[t] = max(H[t−1..t−20])
When:  now_utc = close_time(t) − 1s  → kein Signal
When:  now_utc = close_time(t) + 5s  → RC_ENTRY_BREAKOUT_20D
```

---

## 13. Beispiel (numerisch)

| Variable | Wert |
|---|---|
| C[t] | 95.000 |
| High20[t] (nur H[t−1..t−20]) | 94.200 |
| EMA20_daily[t] | 91.500 |
| ATR14[t] | 2.400 |
| VolumeRatio[t] | 1.05 |
| volume_ratio_min | 1.00 |

Breakout ✓ → Entry, `entry_type = BREAKOUT`

```
StopInitial = 95.000 − 2.5 × 2.400 = 89.000
```

Trailing Update Tag t+5 (ATR14[t+5] = 2.200, C[t+5] = 98.000):

```
1. atr_current = 2.200
2. HighestClose = 98.000
3. trail_candidate = 98.000 − 3.0 × 2.200 = 91.400
4. TrailStop = max(89.000, 91.400) = 91.400
```

Gap-Exit Beispiel: `EffectiveStop = 91.400`, `Open[t+6] = 90.500` → `ExitPrice = 90.500`, `RC_EXIT_STOP_GAP`.

---

## 14. Abnahmekriterien (Strategy V1)

- [ ] High20 ohne Kerze `t`
- [ ] Pullback P1–P6 objektiv testbar
- [ ] Breakout + Pullback gleichzeitig → nur `entry_type = BREAKOUT`
- [ ] Trailing-Update-Reihenfolge §7.3 exakt
- [ ] Gap-Exit: Open wenn `Open < EffectiveStop`
- [ ] Weekly-Trendbruch: kein Exit, nur Entry-Block
- [ ] `volume_ratio_min = 1.00` Baseline; 1.20 Backtest-Variante
- [ ] Warmup: Daily ≥ 21, Weekly ≥ 50, Monthly ≥ 20

---

## Specification Freeze – Version 1.0

Verbindliche Standardparameter (Baseline). Siehe auch Product Spec §Specification Freeze.

| Parameter | Symbol | Standardwert |
|---|---|---|
| Symbole | `SYMBOLS` | BTC, ETH, SOL |
| Monthly EMA Periode | `MONTHLY_EMA_PERIOD` | 20 |
| Weekly EMA fast / slow | `WEEKLY_EMA_FAST` / `WEEKLY_EMA_SLOW` | 20 / 50 |
| Daily EMA Periode | `DAILY_EMA_PERIOD` | 20 |
| Breakout Lookback | `BREAKOUT_LOOKBACK` | 20 (Kerzen `t−1…t−20`) |
| ATR Periode | `ATR_PERIOD` | 14 |
| Volume SMA Periode | `VOLUME_SMA_PERIOD` | 20 |
| Volume Ratio Minimum | `volume_ratio_min` | **1.00** (Backtest-Variante: 1.20) |
| Pullback EMA Toleranz | `pullback_ema_tolerance` | 0.005 |
| Initial Stop ATR-Mult | `stop_initial_atr_mult` | 2.5 |
| Trailing Stop ATR-Mult | `trail_atr_mult` | 3.0 |
| Risiko pro Trade | `risk_per_trade_pct` | 0.5 % |
| Max. Portfoliorisiko | `max_portfolio_risk_pct` | 2.0 % |
| Max. Positionen | `max_open_positions` | 3 |
| Max. Hebel | `max_leverage` | 2.0 |
| Risiko-Rundungstoleranz | `risk_rounding_tolerance` | 0.001 |
| Warmup Daily / Weekly / Monthly | — | ≥ 21 / ≥ 50 / ≥ 20 Kerzen |
| Weekly-Trend Auto-Exit | — | deaktiviert |
| Fear & Greed Filter | — | deaktiviert |

---

## Changelog

| Version | Datum | Änderung |
|---|---|---|
| 1.0.0 | 2026-07-11 | Specification Freeze — Review & Klarstellungen |
