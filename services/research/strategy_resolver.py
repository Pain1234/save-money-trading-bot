"""Standardized strategy interface and resolver (Issue #148 / P4-01b / #265)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from strategy_engine.constants import STRATEGY_VERSION
from strategy_engine.engine import StrategyEngine
from strategy_engine.models import ReasonCode, StrategyParameters, Timeframe

from research.experiment_spec import ALLOWED_SYMBOLS, ExperimentSpec

STRATEGY_INTERFACE_VERSION = "1.0"

# Human-readable parameter help for Research Lab / strategy detail (defaults unchanged).
PARAMETER_DESCRIPTIONS: dict[str, str] = {
    "monthly_ema_period": "Monats-EMA-Periode für das Regime (Close > EMA).",
    "weekly_ema_fast": "Schnelle Wochen-EMA für die Trendbestätigung.",
    "weekly_ema_slow": "Langsame Wochen-EMA für die Trendbestätigung.",
    "daily_ema_period": "Tages-EMA für Pullback-Einstiege.",
    "breakout_lookback": "Lookback in Daily-Kerzen für das 20-Tage-Hoch (Breakout).",
    "atr_period": "ATR-Periode für Stop-Distanz und Trailing.",
    "volume_sma_period": "SMA-Periode für den Volumenfilter.",
    "volume_ratio_min": "Mindest-Volumenratio gegenüber dem Volumen-SMA.",
    "pullback_ema_tolerance": "Toleranzband um die Daily-EMA für Pullback-Bedingungen.",
    "stop_initial_atr_mult": "Initialer Stop als Vielfaches von ATR.",
    "trail_atr_mult": "Trailing-Stop als Vielfaches von ATR (nie lockerer).",
}


@dataclass(frozen=True)
class StrategyCatalogEntry:
    """UI/API metadata for one canonical research strategy (resolver SoT)."""

    strategy_id: str
    display_name: str
    description: str
    strategy_version: str
    aliases: tuple[str, ...]
    supported_symbols: tuple[str, ...]
    required_timeframes: tuple[str, ...]
    lifecycle_status: str
    entrypoint: str
    monthly_filter: str
    weekly_filter: str
    daily_entries: str
    stop_logic: str
    reason_codes: tuple[str, ...]
    parameter_descriptions: dict[str, str]


@dataclass(frozen=True)
class ResolvedStrategy:
    """Pinned, loadable strategy binding for a research run."""

    strategy_id: str
    strategy_version: str
    entrypoint: str
    interface_version: str
    parameters: StrategyParameters
    engine: StrategyEngine


class StrategyResolver(Protocol):
    def resolve(self, spec: ExperimentSpec) -> ResolvedStrategy: ...


_TREND_V1_ENTRYPOINT = "strategy_engine.engine:StrategyEngine"

_TREND_V1 = StrategyCatalogEntry(
    strategy_id="trend_v1",
    display_name="Trend Strategy V1",
    description=(
        "Long-only Multi-Timeframe-Trendstrategie mit Monatsregime, "
        "wöchentlicher Trendbestätigung und täglichem Breakout- oder "
        "Pullback-Einstieg."
    ),
    strategy_version=STRATEGY_VERSION,
    aliases=("trend_strategy_v1",),
    supported_symbols=tuple(sorted(ALLOWED_SYMBOLS)),
    required_timeframes=(
        Timeframe.DAILY.value,
        Timeframe.WEEKLY.value,
        Timeframe.MONTHLY.value,
    ),
    lifecycle_status="active",
    entrypoint=_TREND_V1_ENTRYPOINT,
    monthly_filter=(
        "Monatsregime long, wenn der abgeschlossene Monats-Close über der "
        "Monats-EMA liegt (logisches AND mit den übrigen Filtern)."
    ),
    weekly_filter=(
        "Wochentrend bestätigt, wenn die schnelle Wochen-EMA über der "
        "langsamen Wochen-EMA liegt."
    ),
    daily_entries=(
        "Daily-Einstieg über 20-Tage-Breakout oder objektiv definierten "
        "Pullback an der Daily-EMA; zusätzlich Volumenfilter und Risk Engine."
    ),
    stop_logic=(
        "Initialer ATR-Stop, Trailing-Stop (nie lockerer), Gap-Stop und "
        "Monatsregime-Exit gemäß Strategy Specification V1."
    ),
    reason_codes=tuple(sorted(c.value for c in ReasonCode)),
    parameter_descriptions=dict(PARAMETER_DESCRIPTIONS),
)

# Canonical catalog (exactly one entry per implementation).
_CATALOG: dict[str, StrategyCatalogEntry] = {
    _TREND_V1.strategy_id: _TREND_V1,
}

# Acceptable Spec/Lab IDs → canonical strategy_id (aliases remain readable).
_RESOLVE_MAP: dict[str, str] = {
    _TREND_V1.strategy_id: _TREND_V1.strategy_id,
}
for _alias in _TREND_V1.aliases:
    _RESOLVE_MAP[_alias] = _TREND_V1.strategy_id


def known_strategy_ids() -> tuple[str, ...]:
    """All strategy_ids accepted by DefaultStrategyResolver (canonical + aliases)."""
    return tuple(sorted(_RESOLVE_MAP))


def catalog_strategy_ids() -> tuple[str, ...]:
    """Canonical strategy_ids for UI/API listing (aliases excluded)."""
    return tuple(sorted(_CATALOG))


def canonicalize_strategy_id(strategy_id: str) -> str:
    """Map alias or canonical id to canonical id; raise if unknown."""
    canonical = _RESOLVE_MAP.get(strategy_id)
    if canonical is None:
        msg = f"unknown strategy_id {strategy_id!r}; known: {sorted(_RESOLVE_MAP)}"
        raise ValueError(msg)
    return canonical


def get_strategy_catalog_entry(strategy_id: str) -> StrategyCatalogEntry:
    """Return catalog metadata for a canonical id or known alias."""
    canonical = canonicalize_strategy_id(strategy_id)
    return _CATALOG[canonical]


def list_strategy_catalog() -> tuple[StrategyCatalogEntry, ...]:
    """Stable canonical catalog for Research Workspace listing."""
    return tuple(_CATALOG[sid] for sid in catalog_strategy_ids())


def strategy_ids_equivalent(left: str, right: str) -> bool:
    """True if both ids resolve to the same canonical strategy."""
    try:
        return canonicalize_strategy_id(left) == canonicalize_strategy_id(right)
    except ValueError:
        return False


def _parameters_from_spec(spec: ExperimentSpec) -> StrategyParameters:
    """Map ExperimentSpec.parameters onto StrategyParameters (unknown keys fail)."""
    raw: dict[str, Any] = {"strategy_version": spec.strategy_version}
    for key, value in spec.parameters.items():
        if key == "strategy_id":
            continue
        raw[key] = value
    return StrategyParameters.model_validate(raw)


class DefaultStrategyResolver:
    """Resolve Spec strategy fields to the in-repo Trend Strategy V1 engine."""

    def resolve(self, spec: ExperimentSpec) -> ResolvedStrategy:
        raw_id = str(spec.parameters.get("strategy_id", "trend_v1"))
        try:
            canonical_id = canonicalize_strategy_id(raw_id)
        except ValueError as exc:
            raise ValueError(str(exc)) from exc
        entry = _CATALOG[canonical_id]
        if spec.strategy_version != STRATEGY_VERSION:
            msg = (
                f"unpinned/unsupported strategy_version "
                f"{spec.strategy_version!r}; expected {STRATEGY_VERSION!r}"
            )
            raise ValueError(msg)
        params = _parameters_from_spec(spec)
        engine = StrategyEngine()
        return ResolvedStrategy(
            strategy_id=canonical_id,
            strategy_version=spec.strategy_version,
            entrypoint=entry.entrypoint,
            interface_version=STRATEGY_INTERFACE_VERSION,
            parameters=params,
            engine=engine,
        )


def resolve_strategy(spec: ExperimentSpec) -> ResolvedStrategy:
    """Module-level helper using DefaultStrategyResolver."""
    return DefaultStrategyResolver().resolve(spec)
