"""ExperimentSpec — versioned research experiment contract (Issue #141 / P4-01).

Pins hypothesis, strategy version, cost assumptions, and a P3 DatasetManifest
reference so research runs are comparable and reproducible. Does not embed the
full DatasetManifest; stores dataset_id / optional path + content hash only.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import yaml
from market_data.content_hash import canonical_decimal, canonical_timestamp
from market_data.models import MarketSymbol
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

from research.validation import assert_no_secrets, validate_against_json_schema

EXPERIMENT_SPEC_SCHEMA_VERSION = "1.0"
ALLOWED_SYMBOLS: frozenset[str] = frozenset(s.value for s in MarketSymbol)


class DatasetManifestRef(BaseModel):
    """Pointer to a P3 ``DatasetManifest`` (id/path + content hash)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    dataset_id: str = Field(min_length=1, description="DatasetManifest.dataset_id")
    content_hash: str = Field(
        min_length=64,
        max_length=64,
        pattern=r"^[0-9a-f]{64}$",
        description="DatasetManifest.content_hash (sha256 hex)",
    )
    manifest_path: str | None = Field(
        default=None,
        description="Optional filesystem or catalog path to the manifest document",
    )


class TimeRange(BaseModel):
    """Inclusive research window in UTC."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    start: datetime
    end: datetime

    @field_validator("start", "end", mode="after")
    @classmethod
    def _utc_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            msg = "timestamp must be timezone-aware"
            raise ValueError(msg)
        return value.astimezone(UTC)

    @model_validator(mode="after")
    def _end_after_start(self) -> TimeRange:
        if self.end <= self.start:
            msg = "time_range.end must be after time_range.start"
            raise ValueError(msg)
        return self


class FeeAssumption(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    entry_fee_rate: Decimal = Field(ge=Decimal("0"))
    exit_fee_rate: Decimal = Field(ge=Decimal("0"))


class SlippageAssumption(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    slippage_bps: Decimal = Field(ge=Decimal("0"))


class FundingAssumption(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    enabled: bool = False
    assumed_rate: Decimal | None = Field(
        default=None,
        description="Optional constant funding rate assumption when enabled",
    )


class ExperimentSpec(BaseModel):
    """Fail-closed, versioned experiment specification."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: str = Field(default=EXPERIMENT_SPEC_SCHEMA_VERSION)
    hypothesis: str = Field(min_length=1)
    strategy_version: str = Field(min_length=1)
    parameters: dict[str, Any] = Field(default_factory=dict)
    dataset_manifest_ref: DatasetManifestRef
    symbols: tuple[MarketSymbol, ...] = Field(min_length=1)
    time_range: TimeRange
    starting_capital: Decimal = Field(gt=Decimal("0"))
    fee_assumption: FeeAssumption
    slippage_assumption: SlippageAssumption
    funding_assumption: FundingAssumption
    benchmark: str = Field(min_length=1)
    random_seed: int | None = None
    expected_artifacts: tuple[str, ...] = Field(default_factory=tuple)
    notes: str = ""
    owner: str = Field(min_length=1)

    @field_validator("schema_version")
    @classmethod
    def _supported_schema(cls, value: str) -> str:
        if value != EXPERIMENT_SPEC_SCHEMA_VERSION:
            msg = (
                f"unsupported schema_version {value!r}; "
                f"expected {EXPERIMENT_SPEC_SCHEMA_VERSION!r}"
            )
            raise ValueError(msg)
        return value

    @field_validator("symbols")
    @classmethod
    def _btc_eth_sol_only(cls, value: tuple[MarketSymbol, ...]) -> tuple[MarketSymbol, ...]:
        # MarketSymbol enum already constrains to BTC/ETH/SOL; keep explicit guard.
        bad = [s.value for s in value if s.value not in ALLOWED_SYMBOLS]
        if bad:
            msg = f"symbols outside BTC/ETH/SOL are not allowed: {bad}"
            raise ValueError(msg)
        # Stable, de-duplicated order for deterministic serialization
        ordered = tuple(sorted(set(value), key=lambda s: s.value))
        return ordered


def parse_experiment_spec(data: dict[str, Any], *, check_json_schema: bool = False) -> ExperimentSpec:
    """Validate and parse a raw mapping into ``ExperimentSpec``."""
    assert_no_secrets(data)
    if check_json_schema:
        validate_against_json_schema(data)
    return ExperimentSpec.model_validate(data)


def _canonical_value(value: Any) -> Any:
    if isinstance(value, Decimal):
        return canonical_decimal(value)
    if isinstance(value, datetime):
        return canonical_timestamp(value)
    if isinstance(value, MarketSymbol):
        return value.value
    if isinstance(value, dict):
        return {str(k): _canonical_value(v) for k, v in sorted(value.items(), key=lambda kv: str(kv[0]))}
    if isinstance(value, (list, tuple)):
        return [_canonical_value(v) for v in value]
    return value


def to_canonical_dict(spec: ExperimentSpec) -> dict[str, Any]:
    """JSON-compatible dict with stable key order and decimal/timestamp encoding."""
    raw = spec.model_dump(mode="python")
    canonical = _canonical_value(raw)
    assert isinstance(canonical, dict)
    return canonical


def dumps_canonical(spec: ExperimentSpec) -> bytes:
    """Deterministic UTF-8 JSON bytes (stable key order, compact separators)."""
    payload = json.dumps(
        to_canonical_dict(spec),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return payload.encode("utf-8")


def load_experiment_spec(path: str | Path, *, check_json_schema: bool = False) -> ExperimentSpec:
    """Load ExperimentSpec from a YAML or JSON file."""
    file_path = Path(path)
    text = file_path.read_text(encoding="utf-8")
    suffix = file_path.suffix.lower()
    if suffix in {".yaml", ".yml"}:
        loaded = yaml.safe_load(text)
    elif suffix == ".json":
        loaded = json.loads(text)
    else:
        msg = f"unsupported ExperimentSpec file type: {file_path.suffix!r}"
        raise ValueError(msg)
    if not isinstance(loaded, dict):
        msg = "ExperimentSpec root must be a mapping/object"
        raise ValueError(msg)
    return parse_experiment_spec(loaded, check_json_schema=check_json_schema)


def save_experiment_spec(spec: ExperimentSpec, path: str | Path) -> None:
    """Save ExperimentSpec as deterministic JSON or YAML."""
    file_path = Path(path)
    file_path.parent.mkdir(parents=True, exist_ok=True)
    canonical = to_canonical_dict(spec)
    suffix = file_path.suffix.lower()
    if suffix in {".yaml", ".yml"}:
        # sort_keys for stable YAML mapping order
        text = yaml.safe_dump(
            canonical,
            sort_keys=True,
            default_flow_style=False,
            allow_unicode=True,
        )
        file_path.write_text(text, encoding="utf-8")
    elif suffix == ".json":
        file_path.write_bytes(dumps_canonical(spec) + b"\n")
    else:
        msg = f"unsupported ExperimentSpec file type: {file_path.suffix!r}"
        raise ValueError(msg)
