"""Tests for ExperimentSpec contract (Issue #141 / P4-01)."""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import jsonschema
import pytest
from pydantic import ValidationError
from research.experiment_spec import (
    EXPERIMENT_SPEC_SCHEMA_VERSION,
    dumps_canonical,
    load_experiment_spec,
    parse_experiment_spec,
    save_experiment_spec,
    to_canonical_dict,
)
from research.validation import SCHEMA_PATH, validate_against_json_schema

REPO_ROOT = Path(__file__).resolve().parents[2]
EXAMPLE_JSON = REPO_ROOT / "examples" / "research" / "btc_eth_sol_experiment.example.json"
EXAMPLE_YAML = REPO_ROOT / "examples" / "research" / "btc_eth_sol_experiment.example.yaml"


def _example_dict() -> dict:
    return json.loads(EXAMPLE_JSON.read_text(encoding="utf-8"))


def test_schema_version_present() -> None:
    spec = parse_experiment_spec(_example_dict())
    assert spec.schema_version == EXPERIMENT_SPEC_SCHEMA_VERSION
    assert EXPERIMENT_SPEC_SCHEMA_VERSION == "1.0"
    assert SCHEMA_PATH.is_file()


def test_missing_required_fields_rejected() -> None:
    data = _example_dict()
    del data["hypothesis"]
    with pytest.raises(ValidationError):
        parse_experiment_spec(data)

    data = _example_dict()
    del data["dataset_manifest_ref"]
    with pytest.raises(ValidationError):
        parse_experiment_spec(data)

    data = _example_dict()
    del data["owner"]
    with pytest.raises(ValidationError):
        parse_experiment_spec(data)


def test_unknown_fields_forbidden() -> None:
    data = _example_dict()
    data["unexpected_field"] = "nope"
    with pytest.raises(ValidationError) as exc_info:
        parse_experiment_spec(data)
    assert "unexpected_field" in str(exc_info.value)

    data = _example_dict()
    data["fee_assumption"]["mystery"] = "x"
    with pytest.raises(ValidationError):
        parse_experiment_spec(data)


def test_deterministic_serialization() -> None:
    spec = parse_experiment_spec(_example_dict())
    first = dumps_canonical(spec)
    second = dumps_canonical(spec)
    assert first == second
    # Round-trip via save/load should keep canonical bytes stable for JSON.
    assert first == dumps_canonical(parse_experiment_spec(json.loads(first.decode("utf-8"))))


def test_secrets_rejected() -> None:
    data = _example_dict()
    data["api_key"] = "should-never-appear"
    with pytest.raises(ValueError, match="secrets"):
        parse_experiment_spec(data)

    data = _example_dict()
    data["parameters"] = {"password": "x"}
    with pytest.raises(ValueError, match="secrets"):
        parse_experiment_spec(data)

    data = _example_dict()
    data["parameters"] = {"exchange_token": "x"}
    with pytest.raises(ValueError, match="secrets"):
        parse_experiment_spec(data)


def test_example_btc_eth_sol_validates() -> None:
    spec = load_experiment_spec(EXAMPLE_JSON)
    assert [s.value for s in spec.symbols] == ["BTC", "ETH", "SOL"]
    assert spec.dataset_manifest_ref.content_hash
    assert spec.dataset_manifest_ref.dataset_id

    yaml_spec = load_experiment_spec(EXAMPLE_YAML)
    assert [s.value for s in yaml_spec.symbols] == ["BTC", "ETH", "SOL"]


def test_symbols_outside_btc_eth_sol_rejected() -> None:
    data = _example_dict()
    data["symbols"] = ["BTC", "DOGE"]
    with pytest.raises(ValidationError):
        parse_experiment_spec(data)


def test_json_schema_validation_path() -> None:
    data = _example_dict()
    validate_against_json_schema(data)
    spec = parse_experiment_spec(data, check_json_schema=True)
    assert spec.schema_version == "1.0"

    bad = deepcopy(data)
    bad["symbols"] = ["BTC", "DOGE"]
    with pytest.raises(jsonschema.ValidationError):
        validate_against_json_schema(bad)


def test_save_load_roundtrip_json(tmp_path: Path) -> None:
    spec = load_experiment_spec(EXAMPLE_JSON)
    out = tmp_path / "roundtrip.json"
    save_experiment_spec(spec, out)
    loaded = load_experiment_spec(out)
    assert dumps_canonical(loaded) == dumps_canonical(spec)
    assert to_canonical_dict(loaded)["starting_capital"] == "100000"
