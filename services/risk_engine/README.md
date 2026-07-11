# SAVE-MONEY BOT Risk Engine

Deterministic Python implementation of **Risk Specification V1.0 (Specification Freeze)**.

## Public Interface

```python
from decimal import Decimal
from risk_engine import (
    RiskEngine,
    RiskParameters,
    TradeProposal,
    AccountState,
    SymbolConstraints,
)
from strategy_engine.models import SignalIntentKind

engine = RiskEngine()
decision = engine.evaluate(
    proposal=TradeProposal(
        symbol="BTC",
        entry_price=Decimal("95000"),
        stop_price=Decimal("89000"),
        client_intent_id="intent-uuid-1",
        signal_intent_kind=SignalIntentKind.LONG_ENTRY,
        strategy_approved=True,
    ),
    account=AccountState(
        equity_usd=Decimal("100000"),
        available_margin_usd=Decimal("50000"),
    ),
    constraints=SymbolConstraints(
        quantity_step=Decimal("0.001"),
        minimum_quantity=Decimal("0.001"),
        minimum_notional=Decimal("10"),
        price_tick_size=Decimal("0.01"),
    ),
    open_positions=(),
    open_orders=(),
    processed_intent_ids=frozenset(),
)
```

## Evaluation Order (fail-closed)

1. Account validation (equity, margin, finite values)
2. Symbol constraints (quantity_step, tick_size)
3. Proposal validation (long-only, signal, market data, bot state)
4. Optional loss/drawdown limits (disabled by default)
5. Stop validation (long: `stop < entry`, distance > 0)
6. Duplicate `client_intent_id`
7. Duplicate symbol / open entry order
8. Max open positions
9. Risk-based sizing + floor to `quantity_step`
10. Risk re-check after rounding (§3.4)
11. Leverage cap (reduce only, §6.2)
12. Margin cap (reduce only)
13. Risk re-check after reductions
14. Minimum quantity / minimum notional
15. Projected portfolio risk (actual variant, §4.3)
16. Effective leverage + required margin

## Rounding

```
RiskBudgetUSD = Equity × risk_per_trade_pct
StopDistanceUSD = abs(EntryPrice − StopPrice)
RawQuantity = RiskBudgetUSD / StopDistanceUSD
RoundedQuantity = floor_to_step(RawQuantity, quantity_step)
```

After rounding, quantity is reduced until:

- `ActualTradeRiskUSD ≤ RiskBudgetUSD`
- `ActualTradeRiskPct ≤ risk_per_trade_pct × (1 + risk_rounding_tolerance)`

## Portfolio Risk

```
EffectiveStop_i = max(StopInitial_i, TrailStop_i)
OpenRiskUSD_i = PositionSize_i × max(0, EntryPrice_i − EffectiveStop_i)
CurrentOpenRiskUSD = Σ OpenRiskUSD_i
ProjectedPortfolioRiskUSD = CurrentOpenRiskUSD + ActualTradeRiskUSD_new
```

Approval requires:

```
ProjectedPortfolioRiskUSD ≤ Equity × max_portfolio_risk_pct
```

## Leverage & Margin

```
NotionalUSD = RoundedQuantity × EntryPrice
RequiredMarginUSD = NotionalUSD / max_leverage
EffectiveLeverage = ProjectedNotional / Equity
```

Leverage **never increases** risk-based quantity — only `min()` reductions per §6.2.

## Default Parameters (Freeze 1.0)

| Parameter | Value |
|---|---|
| `risk_per_trade_pct` | `0.005` (0.5 %) |
| `max_portfolio_risk_pct` | `0.02` (2.0 %) |
| `max_open_positions` | `3` |
| `max_leverage` | `2.0` |
| `risk_rounding_tolerance` | `0.001` |

## Reason Codes (from frozen spec)

| Code | Use |
|---|---|
| `RC_RISK_APPROVED` | All checks passed |
| `RC_REJECT_RISK_TRADE` | Trade risk / min size / min notional |
| `RC_REJECT_RISK_PORTFOLIO` | Portfolio risk exceeded |
| `RC_REJECT_MAX_POSITIONS` | ≥ 3 positions |
| `RC_REJECT_DUPLICATE_SYMBOL` | Symbol open or conflicting order |
| `RC_REJECT_LEVERAGE` | Leverage/margin limit after reduction |
| `RC_REJECT_DATA` | Invalid account, stop, market data, duplicate intent |
| `RC_REJECT_NO_SIGNAL` | Strategy not approved / wrong signal |

## Example (from Risk Spec §11)

Equity 100.000, Entry 95.000, Stop 89.000, step 0.001:

```
RiskBudget = 500
StopDistance = 6.000
RawQuantity ≈ 0.0833
RoundedQuantity = 0.083
ActualRisk = 498 USD (0.498 %)
```

## Loss / Drawdown Limits (V1)

Disabled by default (`LossLimitConfig`). When enabled, missing threshold values → fail-closed.

## Test Commands

```bash
pip install -e ".[dev]"
python -m pytest tests/risk_engine -v
python -m mypy services/risk_engine
python -m ruff check services/risk_engine
```

## Open Specification Questions

1. **Duplicate `client_intent_id`:** No dedicated reason code in freeze — mapped to `RC_REJECT_DATA`.
2. **Daily/weekly loss & drawdown limits:** No numeric V1 defaults in spec — implemented as optional config; rejections use `RC_REJECT_DATA`.
3. **Minimum notional reject:** Spec references exchange limits; mapped to `RC_REJECT_RISK_TRADE`.
4. **Conflicting open entry order:** Mapped to `RC_REJECT_DUPLICATE_SYMBOL` (same symbol collision).

## Not Implemented

- Order execution, Hyperliquid API, database, WebSockets
- Automatic limit changes
