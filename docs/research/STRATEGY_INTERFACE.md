# Strategy interface and resolver (#148)

Interface version: `1.0` (`STRATEGY_INTERFACE_VERSION` in `services/research/strategy_resolver.py`).

## Inputs (from ExperimentSpec)

| Field | Role |
|-------|------|
| `strategy_version` | Must match pinned `strategy_engine.constants.STRATEGY_VERSION` |
| `parameters.strategy_id` | Resolver key (default `trend_v1`) |
| `parameters.*` | Mapped onto `StrategyParameters` (unknown keys fail validation) |

Git commit is pinned separately on the RunManifest / `run_id` inputs (`#142`), not inside the resolver.

## Outputs (`ResolvedStrategy`)

| Field | Meaning |
|-------|---------|
| `strategy_id` | Resolved id |
| `strategy_version` | Pinned version string |
| `entrypoint` | Module path of the implementation |
| `interface_version` | Strategy interface schema version |
| `parameters` | Validated `StrategyParameters` |
| `engine` | Loadable `StrategyEngine` instance |

## Resolver contract

- `DefaultStrategyResolver.resolve(spec)` maps Spec → `ResolvedStrategy` deterministically.
- Known ids today: `trend_v1`, `trend_strategy_v1` → `strategy_engine.engine:StrategyEngine`.
- Unknown `strategy_id` → **fail closed** (`ValueError`).
- Mismatched / unpinned `strategy_version` → **fail closed**.
- Same Spec + same code → same resolution (no ambient registry lookup).

## Research signal semantics

At research level the runner injects the resolved `StrategyEngine` into
`BacktestEngine(strategy=resolved.engine)` — there is no second parallel
strategy resolution. Signal/order evaluation is identical to the backtester
path used by paper parity tests (`#48`).

## Out of scope (not P4)

- New trading rules or parameter optimization
- Live-trading adapters
- Multi-asset strategy universe (P7)
- OOS / walk-forward (P5)
