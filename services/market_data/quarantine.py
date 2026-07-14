"""Invalid dataset quarantine (#82)."""

from __future__ import annotations

from dataclasses import dataclass

from market_data.dataset_catalog import DatasetCatalog
from market_data.dataset_quality import DatasetQualityReportRecord, evaluate_dataset_quality
from market_data.manifest import DatasetManifest
from market_data.models import DataQualityStatus, MarketSymbol, MarketTimeframe
from market_data.timeframes import ensure_utc


class QuarantineError(Exception):
    """Dataset blocked for research use."""

    def __init__(self, message: str, *, dataset_id: str, status: DataQualityStatus) -> None:
        super().__init__(message)
        self.dataset_id = dataset_id
        self.status = status


@dataclass(frozen=True)
class QuarantineDecision:
    dataset_id: str
    allowed: bool
    status: DataQualityStatus
    warnings: tuple[str, ...]


_BLOCKING_STATUSES = frozenset({DataQualityStatus.INVALID, DataQualityStatus.DISCONNECTED})


def assess_quarantine(
    manifest: DatasetManifest,
    report: DatasetQualityReportRecord,
) -> QuarantineDecision:
    status = report.report.status
    warnings = tuple(manifest.known_issues)
    if status in _BLOCKING_STATUSES:
        return QuarantineDecision(
            dataset_id=manifest.dataset_id or "",
            allowed=False,
            status=status,
            warnings=warnings,
        )
    if status in {DataQualityStatus.INCOMPLETE, DataQualityStatus.STALE}:
        return QuarantineDecision(
            dataset_id=manifest.dataset_id or "",
            allowed=True,
            status=status,
            warnings=warnings + (f"quality_status={status.value}",),
        )
    return QuarantineDecision(
        dataset_id=manifest.dataset_id or "",
        allowed=True,
        status=status,
        warnings=warnings,
    )


def require_research_dataset(
    catalog: DatasetCatalog,
    dataset_id: str,
    symbol: MarketSymbol,
    timeframe: MarketTimeframe,
    evaluation_time,
) -> DatasetManifest:
    """Fail-closed lookup for research consumption."""
    manifest = catalog.get_manifest(dataset_id)
    report = evaluate_dataset_quality(
        catalog,
        dataset_id,
        symbol,
        timeframe,
        ensure_utc(evaluation_time),
    )
    decision = assess_quarantine(manifest, report)
    if not decision.allowed:
        raise QuarantineError(
            f"dataset {dataset_id} quarantined: {decision.status.value}",
            dataset_id=dataset_id,
            status=decision.status,
        )
    return manifest
