"""Canonical instrument identity types."""

from __future__ import annotations

from typing import NewType

from pydantic import BaseModel, ConfigDict, Field, field_validator

from instruments.enums import AssetClass, InstrumentType, Network, Venue

InstrumentId = NewType("InstrumentId", str)


def make_instrument_id(
    *,
    venue: Venue,
    network: Network,
    instrument_type: InstrumentType,
    base_symbol: str,
) -> InstrumentId:
    """Build a stable, comparable InstrumentId (not a provider-internal key)."""
    base = base_symbol.strip().upper()
    if not base:
        raise ValueError("base_symbol must be non-empty")
    return InstrumentId(f"{venue.value}:{network.value}:{instrument_type.value}:{base}")


def parse_instrument_id(value: str | InstrumentId) -> tuple[Venue, Network, InstrumentType, str]:
    """Parse InstrumentId into components; fail-closed on malformed ids."""
    raw = str(value).strip()
    parts = raw.split(":")
    if len(parts) != 4:
        raise ValueError(f"Invalid InstrumentId: {value!r}")
    venue_s, network_s, type_s, base = parts
    try:
        venue = Venue(venue_s)
        network = Network(network_s)
        instrument_type = InstrumentType(type_s)
    except ValueError as exc:
        raise ValueError(f"Invalid InstrumentId: {value!r}") from exc
    base_symbol = base.strip().upper()
    if not base_symbol:
        raise ValueError(f"Invalid InstrumentId: {value!r}")
    return venue, network, instrument_type, base_symbol


class Instrument(BaseModel):
    """Canonical instrument identity used by P4 research / universe layers."""

    model_config = ConfigDict(frozen=True)

    instrument_id: InstrumentId
    venue: Venue
    network: Network
    instrument_type: InstrumentType
    asset_class: AssetClass
    base_symbol: str = Field(min_length=1)
    quote_symbol: str = Field(default="USD", min_length=1)
    legacy_symbol: str = Field(min_length=1)
    display_name: str = Field(min_length=1)
    active: bool = True

    @field_validator("instrument_id", mode="before")
    @classmethod
    def _coerce_instrument_id(cls, value: object) -> InstrumentId:
        # InstrumentId is a NewType(str); runtime values are plain strings.
        if isinstance(value, str):
            return InstrumentId(value)
        raise TypeError("instrument_id must be a string InstrumentId")

    @field_validator("base_symbol", "legacy_symbol", "quote_symbol")
    @classmethod
    def _upper_symbols(cls, value: str) -> str:
        normalized = value.strip().upper()
        if not normalized:
            raise ValueError("symbol fields must be non-empty")
        return normalized

    def model_post_init(self, __context: object) -> None:
        expected = make_instrument_id(
            venue=self.venue,
            network=self.network,
            instrument_type=self.instrument_type,
            base_symbol=self.base_symbol,
        )
        if self.instrument_id != expected:
            raise ValueError(
                f"instrument_id {self.instrument_id!r} does not match identity "
                f"components (expected {expected!r})"
            )
