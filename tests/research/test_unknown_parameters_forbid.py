"""AUD-P1-002 / #375: unknown strategy parameters fail before identity/run creation."""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import pytest
from pydantic import ValidationError
from research.experiment_spec import parse_experiment_spec
from research.identity import compute_experiment_id
from research.strategy_resolver import resolve_strategy
from strategy_engine.models import StrategyParameters

REPO_ROOT = Path(__file__).resolve().parents[2]
EXAMPLE_JSON = REPO_ROOT / "examples" / "research" / "btc_eth_sol_experiment.example.json"


def _example_dict() -> dict:
    return json.loads(EXAMPLE_JSON.read_text(encoding="utf-8"))


def test_misspelled_parameter_rejected_at_spec_parse() -> None:
    data = _example_dict()
    data["parameters"] = {**data["parameters"], "misspelled_parameter": 1}
    with pytest.raises(ValidationError, match="misspelled_parameter"):
        parse_experiment_spec(data)


def test_unknown_parameter_rejected_by_strategy_parameters_model() -> None:
    with pytest.raises(ValidationError, match="misspelled_parameter"):
        StrategyParameters.model_validate({"misspelled_parameter": 99})


def test_omitted_parameters_bind_to_effective_defaults() -> None:
    data = _example_dict()
    data["parameters"] = {}
    spec = parse_experiment_spec(data)
    expected = StrategyParameters(strategy_version=spec.strategy_version).model_dump(
        mode="json"
    )
    del expected["strategy_version"]
    assert spec.parameters == expected
    resolved = resolve_strategy(spec)
    assert resolved.parameters.model_dump(mode="json") == {
        **expected,
        "strategy_version": spec.strategy_version,
    }


def test_partial_and_explicit_defaults_share_experiment_id() -> None:
    full = parse_experiment_spec(_example_dict())
    partial_data = _example_dict()
    # Omit one field that matches the frozen default — identity must still match
    # the fully explicit effective snapshot.
    del partial_data["parameters"]["monthly_ema_period"]
    partial = parse_experiment_spec(partial_data)
    assert partial.parameters["monthly_ema_period"] == full.parameters["monthly_ema_period"]
    assert compute_experiment_id(partial) == compute_experiment_id(full)


def test_strategy_id_meta_key_allowed() -> None:
    data = _example_dict()
    data["parameters"] = {**data["parameters"], "strategy_id": "trend_v1"}
    spec = parse_experiment_spec(data)
    assert spec.parameters["strategy_id"] == "trend_v1"
    resolve_strategy(spec)


def test_unknown_key_never_reaches_identity() -> None:
    data = _example_dict()
    polluted = deepcopy(data)
    polluted["parameters"] = {**data["parameters"], "typo_atr_perdiod": 14}
    with pytest.raises(ValidationError):
        parse_experiment_spec(polluted)
