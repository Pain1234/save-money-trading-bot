"""Standardized strategy interface and resolver (Issue #148 / P4-01b)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from strategy_engine.constants import STRATEGY_VERSION
from strategy_engine.engine import StrategyEngine
from strategy_engine.models import StrategyParameters

from research.experiment_spec import ExperimentSpec

STRATEGY_INTERFACE_VERSION = "1.0"


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


_KNOWN: dict[str, str] = {
    "trend_v1": "strategy_engine.engine:StrategyEngine",
    "trend_strategy_v1": "strategy_engine.engine:StrategyEngine",
}


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
        strategy_id = str(spec.parameters.get("strategy_id", "trend_v1"))
        entrypoint = _KNOWN.get(strategy_id)
        if entrypoint is None:
            msg = (
                f"unknown strategy_id {strategy_id!r}; "
                f"known: {sorted(_KNOWN)}"
            )
            raise ValueError(msg)
        if spec.strategy_version != STRATEGY_VERSION:
            msg = (
                f"unpinned/unsupported strategy_version "
                f"{spec.strategy_version!r}; expected {STRATEGY_VERSION!r}"
            )
            raise ValueError(msg)
        params = _parameters_from_spec(spec)
        engine = StrategyEngine()
        return ResolvedStrategy(
            strategy_id=strategy_id,
            strategy_version=spec.strategy_version,
            entrypoint=entrypoint,
            interface_version=STRATEGY_INTERFACE_VERSION,
            parameters=params,
            engine=engine,
        )


def resolve_strategy(spec: ExperimentSpec) -> ResolvedStrategy:
    """Module-level helper using DefaultStrategyResolver."""
    return DefaultStrategyResolver().resolve(spec)
