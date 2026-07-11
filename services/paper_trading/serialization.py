"""Serialize strategy evaluation results for persistence."""

from __future__ import annotations

from typing import Any

from strategy_engine.models import StrategyEvaluation


def evaluation_to_regime_result(evaluation: StrategyEvaluation) -> dict[str, Any]:
    return evaluation.monthly_regime.model_dump(mode="json")


def evaluation_to_entry_result(evaluation: StrategyEvaluation) -> dict[str, Any]:
    return {
        "breakout": evaluation.breakout_result.model_dump(mode="json"),
        "pullback": evaluation.pullback_result.model_dump(mode="json"),
        "selected_entry_type": (
            evaluation.selected_entry_type.value if evaluation.selected_entry_type else None
        ),
        "signal_intent": evaluation.signal_intent.model_dump(mode="json"),
        "atr": str(evaluation.atr) if evaluation.atr is not None else None,
        "volume_ratio": (
            str(evaluation.volume_ratio) if evaluation.volume_ratio is not None else None
        ),
    }


def evaluation_rejection_reasons(evaluation: StrategyEvaluation) -> tuple[str, ...]:
    return tuple(str(c) for c in evaluation.reason_codes)


def evaluation_hash_payload(
    evaluation: StrategyEvaluation,
    *,
    daily_candle_open_time: str,
) -> dict[str, Any]:
    return {
        "symbol": evaluation.symbol,
        "strategy_version": evaluation.strategy_version,
        "evaluation_time": evaluation.evaluation_time.isoformat(),
        "daily_candle_open_time": daily_candle_open_time,
        "signal_kind": evaluation.signal_intent.kind.value,
        "selected_entry_type": (
            evaluation.selected_entry_type.value if evaluation.selected_entry_type else None
        ),
        "atr": str(evaluation.atr) if evaluation.atr is not None else None,
        "reason_codes": [str(c) for c in evaluation.reason_codes],
    }
