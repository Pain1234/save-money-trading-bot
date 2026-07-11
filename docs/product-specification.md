# SAVE-MONEY BOT — Product Specification

**Version:** 1.0.0 (Specification Freeze)  
**Status:** Verbindlich (Design-Freeze UI unverändert)  
**Scope:** Privates Hyperliquid Perpetual-Trading-Dashboard & Bot  
**Strategie-Referenz:** [strategy-specification.md](./strategy-specification.md)  
**Risiko-Referenz:** [risk-specification.md](./risk-specification.md)

---

## 1. Produktziel

SAVE-MONEY BOT ist ein **privates**, automatisiertes Long-only-Trading-System für BTC-, ETH- und SOL-Perpetuals auf Hyperliquid. Das Produkt besteht aus:

1. **Dashboard (UI)** — Monitoring, Steuerung, Mock-/Live-Anzeige (Design-Freeze, keine Änderung)
2. **Strategy Engine** — Signalgenerierung gemäß Strategy V1
3. **Risk Engine** — Positionsgröße, Stops, Portfolio-Limits gemäß Risk Spec
4. **Execution Layer** — Orderplatzierung auf Hyperliquid (Implementierung folgt)

Dieses Dokument definiert **Was** das System leistet, **nicht** den UI-Code.

---

## 2. Nicht-Ziele (V1)

- Kein Short-Trading
- Keine Multi-Exchange-Anbindung
- Kein Fear-&-Greed-basierter Filter (nur Speicherung & Anzeige)
- Keine Options-/Spot-Strategien
- Kein Social/Copy-Trading
- Keine Änderung am eingefrorenen Dashboard-Design

---

## 3. Unterstützte Märkte

| Symbol | Hyperliquid Perpetual |
|---|---|
| BTC | `BTC` |
| ETH | `ETH` |
| SOL | `SOL` |

Exchange-Metadaten (pro Symbol, zur Laufzeit von Hyperliquid geladen):

| Feld | Verwendung |
|---|---|
| `tick_size` | Preis-Rundung (Stops, Limits) |
| `quantity_step` | Positionsgrößen-Rundung (floor) |
| `min_order_size` | Mindest-Ordermenge |

**V1:** Long-only, maximal **eine offene Position pro Symbol**, maximal **drei Positionen gesamt**.

---

## 4. Systemarchitektur (logisch)

```
Marktdaten (Hyperliquid OHLCV, UTC)
        ↓
Indikator-Pipeline (Monthly / Weekly / Daily)
        ↓
Strategy Engine V1 (Entry/Exit-Signale)
        ↓
Risk Engine (Sizing, Stops, Limits)
        ↓
Execution (Orders) — späterer Sprint
        ↓
Dashboard (Anzeige, Steuerung, Logs)
```

**Datenfluss-Regel:** Signale basieren ausschließlich auf **abgeschlossenen Kerzen** (Strategy Spec §2).

---

## 5. Zeit & UTC

| Aspekt | Regel |
|---|---|
| Referenzzeitzone | **UTC** (ausschließlich) |
| Daily-Kerze | `open_time = YYYY-MM-DD 00:00:00 UTC`, `close_time = YYYY-MM-DD 23:59:59 UTC` (inklusiv) |
| Weekly-Kerze | Montag `00:00:00 UTC` bis Sonntag `23:59:59 UTC` (ISO-Woche, Start Montag) |
| Monthly-Kerze | `YYYY-MM-01 00:00:00 UTC` bis letzter Tag `23:59:59 UTC` |
| Kerze geschlossen | `now_utc >= close_time` |
| Timestamps in Logs | ISO-8601 mit `Z`-Suffix |

---

## 6. Marktdaten-Anforderungen

### 6.1 Benötigte Felder pro Kerze

| Feld | Typ | Pflicht |
|---|---|---|
| `open_time` | UTC datetime | ja |
| `close_time` | UTC datetime (inklusiv, siehe §5) | ja |
| `open`, `high`, `low`, `close` | float > 0 | ja |
| `volume` | float ≥ 0 | ja (Daily) |

### 6.2 Warmup (Hard Block)

Warmup ist pro Symbol erfüllt, wenn **alle** Bedingungen aus Strategy Spec §3.1 erfüllt sind. Keine Entries im Status `WARMUP`.

### 6.3 Datenqualität

| Zustand | Verhalten |
|---|---|
| Fehlende Kerze in Sequenz | `DATA_GAP` → kein Entry bis Lücke geschlossen |
| `close <= 0` oder `volume < 0` | Kerze verwerfen, `RC_REJECT_DATA` |
| Stale Feed (> 2× Kerzenintervall nach erwartetem Close) | `DATA_STALE`, keine neuen Entries |
| API-Ausfall | `DEGRADED`; offene Stops bleiben aktiv |

---

## 7. Fear & Greed Index

| Aspekt | V1-Verhalten |
|---|---|
| Quelle | Externe API (konfigurierbar) |
| Speicherung | Täglicher Snapshot, UTC-Timestamp |
| Dashboard | Anzeige (bestehendes UI) |
| Strategie-Einfluss | **Keiner** |
| Filter-UI im Dashboard | Kosmetisch/informativ in V1 |

---

## 8. Bot-Zustände

| Status | Beschreibung |
|---|---|
| `OFF` | Keine Signale, keine Orders |
| `WARMUP` | Historie unvollständig |
| `ACTIVE` | Signale & Risk-Checks aktiv |
| `PAUSED` | Keine neuen Entries; Exits/Stops aktiv |
| `DEGRADED` | Daten-/API-Problem; keine neuen Entries |
| `ERROR` | Manueller Eingriff erforderlich |

---

## 9. Entry- & Exit-Übersicht (V1)

### Entry (Long, alle Bedingungen AND)

1. Monthly Regime: `Close_month > EMA20_month`
2. Weekly Trend: `EMA20_week > EMA50_week` (Entry-Filter; **kein** Auto-Exit bei Bruch)
3. Daily Entry: Breakout **oder** Pullback (max. **eine** Orderabsicht; Breakout-Priorität)
4. Volume Ratio ≥ `volume_ratio_min` (Baseline **1,00**)
5. Risk Engine: Slot frei, `projected_portfolio_risk_pct` ≤ Limit, Hebel OK

### Exit

1. Stop (Initial oder Trailing) — inkl. Gap-Regel (Open unter Stop → Exit zu Open)
2. Monthly Regime-Exit: `Close_month ≤ EMA20_month`
3. Manueller Exit (späterer Sprint)

**Kein Exit V1:** Weekly-Trendbruch (`EMA20_week ≤ EMA50_week`).

Details: [strategy-specification.md](./strategy-specification.md)

---

## 10. Reason Codes (Produkt-Ebene)

Vollständige, konsistente Liste in Strategy Spec §10 und Risk Spec §13.

| Kategorie | Beispiele |
|---|---|
| Entry | `RC_ENTRY_BREAKOUT_20D`, `RC_ENTRY_PULLBACK_EMA20` |
| Exit | `RC_EXIT_STOP_INITIAL`, `RC_EXIT_STOP_TRAILING`, `RC_EXIT_STOP_GAP`, `RC_EXIT_REGIME_MONTHLY` |
| Reject | `RC_REJECT_VOLUME`, `RC_REJECT_RISK_TRADE`, `RC_REJECT_RISK_PORTFOLIO`, … |

Jede Orderabsicht enthält zusätzlich `entry_type ∈ { BREAKOUT, PULLBACK }` (Strategy Spec §5.6).

---

## 11. Look-ahead-Bias-Schutz

1. Indikatoren nur mit geschlossenen Kerzen bis Index `t`.
2. `High20[t]` ausschließlich aus Kerzen `t−1 … t−20` (Kerze `t` ausgeschlossen).
3. Entry-Signale erst nach Daily-Close-Event.
4. Backtest-Engine identische Close-Regeln (Strategy Spec §12).

---

## 12. Fehlerfälle (Produkt)

| Fehler | Reaktion |
|---|---|
| Hyperliquid API timeout | Retry 3×; danach `DEGRADED` |
| Order rejected (margin) | `EXEC_MARGIN_REJECT` |
| Order rejected (min size) | `EXEC_MIN_SIZE` |
| Partial fill | Size/Stop/Risiko neu berechnen |
| Stop order failed | `ERROR`, Alert |
| DB ≠ Exchange Position | `ERROR`, Reconciliation, Freeze Entries |

---

## 13. Abnahmekriterien (Produkt V1)

- [ ] BTC, ETH, SOL identische Regellogik
- [ ] Kein Entry ohne Regime + Weekly Trend + Daily Signal + Volume Ratio
- [ ] `volume_ratio_min = 1.00` als Baseline; Backtest-Variante 1.20 separat dokumentiert
- [ ] Breakout-Priorität: nur eine Orderabsicht mit `entry_type = BREAKOUT`
- [ ] Gap-Stop: Exit-Preis = Open wenn `Open < EffectiveStop`
- [ ] Weekly-Trendbruch: kein Auto-Exit
- [ ] Positionsgröße nach `quantity_step` (floor), Risiko-Nachtest
- [ ] Hebel erhöht nie das Kontorisiko
- [ ] Fear & Greed ohne Signaleinfluss
- [ ] Dashboard-Design unverändert

---

## 14. Glossar

| Begriff | Definition |
|---|---|
| **Equity** | `AccountBalance + UnrealizedPnL` (USD) |
| **Current Open Risk** | Summe offener Risiken bis `EffectiveStop` (Risk Spec §4) |
| **Projected Portfolio Risk** | `Current Open Risk + RiskBudget_new` |
| **entry_type** | `BREAKOUT` oder `PULLBACK` |
| **Closed Candle** | `now_utc >= close_time` |

---

## Specification Freeze – Version 1.0

Verbindliche Standardparameter (Baseline). Änderungen nur mit expliziter Spec-Revision.

| Parameter | Symbol | Standardwert | Anmerkung |
|---|---|---|---|
| Symbole | `SYMBOLS` | BTC, ETH, SOL | fest |
| Richtung | — | Long-only | fest |
| Monthly EMA Periode | `MONTHLY_EMA_PERIOD` | 20 | fest |
| Weekly EMA fast | `WEEKLY_EMA_FAST` | 20 | fest |
| Weekly EMA slow | `WEEKLY_EMA_SLOW` | 50 | fest |
| Daily EMA Periode | `DAILY_EMA_PERIOD` | 20 | fest |
| Breakout Lookback | `BREAKOUT_LOOKBACK` | 20 | Kerzen `t−1…t−20` |
| ATR Periode | `ATR_PERIOD` | 14 | Wilder, Daily |
| Volume SMA Periode | `VOLUME_SMA_PERIOD` | 20 | Daily |
| Volume Ratio Minimum | `volume_ratio_min` | **1.00** | konfigurierbar; Backtest-Variante **1.20** |
| Pullback EMA Toleranz | `pullback_ema_tolerance` | 0.005 (0,5 %) | konfigurierbar |
| Initial Stop ATR-Multiplikator | `stop_initial_atr_mult` | 2.5 | fest |
| Trailing Stop ATR-Multiplikator | `trail_atr_mult` | 3.0 | fest |
| Risiko pro Trade | `risk_per_trade_pct` | 0.5 % | fest |
| Max. Portfoliorisiko | `max_portfolio_risk_pct` | 2.0 % | fest |
| Max. Positionen | `max_open_positions` | 3 | fest |
| Max. Hebel | `max_leverage` | 2.0 | Margin-Effizienz, kein Risiko-Boost |
| Risiko-Rundungstoleranz | `risk_rounding_tolerance` | 0.001 (0,1 %) | nach `quantity_step` |
| Weekly-Trend Auto-Exit | — | **deaktiviert** | V1 |
| Fear & Greed Filter | — | **deaktiviert** | nur Anzeige |
| Daily-Auswertung | — | 00:00:05 UTC | fest |
| Weekly-Auswertung | — | Montag 00:00:10 UTC | fest |
| Monthly-Auswertung | — | 1. des Monats 00:00:15 UTC | fest |

---

## Changelog

| Version | Datum | Änderung |
|---|---|---|
| 1.0.0 | 2026-07-11 | Specification Freeze — Review & Klarstellungen |
