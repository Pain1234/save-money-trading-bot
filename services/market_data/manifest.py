"""Dataset manifest schema and validation (Issue #77)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from market_data.content_hash import derive_dataset_id
from market_data.models import DataQualityStatus, MarketSymbol, MarketTimeframe


class DatasetManifest(BaseModel):
    """Versioned research dataset manifest."""

    model_config = ConfigDict(frozen=True)

    schema_version: str = Field(default="1.0")
    source: str = Field(description="e.g. hyperliquid/mainnet")
    symbols: tuple[MarketSymbol, ...]
    timeframes: tuple[MarketTimeframe, ...]
    start_timestamp: datetime
    end_timestamp: datetime
    timezone: str = Field(default="UTC")
    row_count: int = Field(ge=0)
    content_hash: str = Field(min_length=64, max_length=64)
    raw_dataset_id: str = Field(min_length=1)
    raw_content_hash: str = Field(min_length=64, max_length=64)
    import_configuration: dict[str, Any] = Field(default_factory=dict)
    code_commit: str = Field(min_length=7)
    created_at: datetime
    parent_dataset_id: str | None = None
    quality_status: DataQualityStatus = DataQualityStatus.VALID
    allow_quality_warnings: bool = Field(
        default=False,
        description="Explicit approval to use STALE/INCOMPLETE datasets for research",
    )
    known_issues: tuple[str, ...] = Field(default_factory=tuple)
    dataset_id: str | None = None
    layer: str = Field(default="normalized", description="normalized | derived")

    @field_validator(
        "start_timestamp",
        "end_timestamp",
        "created_at",
        mode="after",
    )
    @classmethod
    def _utc_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            msg = "timestamp must be timezone-aware"
            raise ValueError(msg)
        return value.astimezone(UTC)

    def with_dataset_id(self) -> DatasetManifest:
        """Return copy with deterministic dataset_id assigned."""
        dataset_id = derive_dataset_id(self.content_hash, self.schema_version, self.source)
        return self.model_copy(update={"dataset_id": dataset_id})

    def to_catalog_dict(self) -> dict[str, Any]:
        data = self.model_dump(mode="json")
        if data.get("dataset_id") is None:
            data["dataset_id"] = derive_dataset_id(
                self.content_hash,
                self.schema_version,
                self.source,
            )
        return data


def parse_manifest(data: dict[str, Any]) -> DatasetManifest:
    manifest = DatasetManifest.model_validate(data)
    return manifest.with_dataset_id()
