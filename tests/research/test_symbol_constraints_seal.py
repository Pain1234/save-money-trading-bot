"""Tests for sealed research symbol constraints (#363)."""

from __future__ import annotations

import json
from copy import deepcopy
from decimal import Decimal
from pathlib import Path

import pytest
from pydantic import ValidationError
from research.experiment_spec import parse_experiment_spec
from research.runner import _config_from_spec
from research.strategy_resolver import resolve_strategy
from research.symbol_constraints import (
    HYPERLIQUID_MAINNET_CONSTRAINT_SET_VERSION,
    HYPERLIQUID_MAINNET_V1_CONTENT_HASH,
    HYPERLIQUID_MAINNET_V1_PINS,
    compute_constraint_set_content_hash,
    hyperliquid_mainnet_v1_pins,
)

from tests.research.spec_fixtures import with_sealed_symbol_constraints

REPO = Path(__file__).resolve().parents[2]
EXAMPLE = REPO / "examples" / "research" / "btc_eth_sol_experiment.example.json"


def test_hl_v1_pins_are_stable() -> None:
    assert HYPERLIQUID_MAINNET_CONSTRAINT_SET_VERSION == "hl-mainnet-szdecimals-v1"
    assert compute_constraint_set_content_hash(HYPERLIQUID_MAINNET_V1_PINS) == (
        HYPERLIQUID_MAINNET_V1_CONTENT_HASH
    )
    assert HYPERLIQUID_MAINNET_V1_PINS["BTC"]["quantity_step"] == "0.00001"
    assert HYPERLIQUID_MAINNET_V1_PINS["ETH"]["quantity_step"] == "0.0001"
    assert HYPERLIQUID_MAINNET_V1_PINS["SOL"]["quantity_step"] == "0.01"


def test_example_spec_includes_sealed_constraints() -> None:
    raw = json.loads(EXAMPLE.read_text(encoding="utf-8"))
    assert "symbol_constraints" in raw
    spec = parse_experiment_spec(raw, check_json_schema=True)
    assert set(spec.symbol_constraints) == {"BTC", "ETH", "SOL"}
    resolved = resolve_strategy(spec)
    config = _config_from_spec(spec, resolved.parameters)
    assert set(config.symbol_constraints) == {"BTC", "ETH", "SOL"}
    assert config.symbol_constraints["BTC"].quantity_step == Decimal("0.00001")


def test_missing_symbol_constraints_rejected() -> None:
    raw = json.loads(EXAMPLE.read_text(encoding="utf-8"))
    del raw["symbol_constraints"]
    with pytest.raises(ValidationError):
        parse_experiment_spec(raw)


def test_constraints_must_match_symbols_exactly() -> None:
    raw = json.loads(EXAMPLE.read_text(encoding="utf-8"))
    raw["symbols"] = ["BTC", "ETH"]
    with pytest.raises(ValidationError, match="symbol_constraints must cover exactly"):
        parse_experiment_spec(raw)


def test_constraint_mutation_changes_content_hash() -> None:
    pins = hyperliquid_mainnet_v1_pins(("BTC",))
    mutated = deepcopy(pins)
    mutated["BTC"]["minimum_notional"] = "11"
    assert compute_constraint_set_content_hash(pins) != compute_constraint_set_content_hash(
        mutated
    )


def test_fixture_helper_injects_pins() -> None:
    raw = {"symbols": ["BTC"], "hypothesis": "x"}
    out = with_sealed_symbol_constraints(raw)
    assert out["symbol_constraints"]["BTC"]["quantity_step"] == "0.00001"
