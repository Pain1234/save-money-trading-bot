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
_WARNING_STATUSES = frozenset({DataQualityStatus.INCOMPLETE, DataQualityStatus.STALE})


def _quality_warnings(report: DatasetQualityReportRecord) -> tuple[str, ...]:
    warnings: list[str] = []
    if report.report.status != DataQualityStatus.VALID:
        warnings.append(f"quality_status={report.report.status.value}")
    if report.gap_count:
        warnings.append(f"gap_count={report.gap_count}")
    if report.conflict_count:
        warnings.append(f"conflict_count={report.conflict_count}")
    if report.stale:
        warnings.append("stale=true")
    warnings.extend(report.report.messages)
    return tuple(warnings)


def assess_quarantine(
    manifest: DatasetManifest,
    report: DatasetQualityReportRecord,
) -> QuarantineDecision:
    status = report.report.status
    warnings = _quality_warnings(report)
    if status in _BLOCKING_STATUSES:
        return QuarantineDecision(
            dataset_id=manifest.dataset_id or "",
            allowed=False,
            status=status,
            warnings=warnings,
        )
    if status in _WARNING_STATUSES:
        allowed = manifest.allow_quality_warnings
        return QuarantineDecision(
            dataset_id=manifest.dataset_id or "",
            allowed=allowed,
            status=status,
            warnings=warnings,
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
        persist=False,
    )
    decision = assess_quarantine(manifest, report)
    issue_updates = decision.warnings if decision.warnings else None
    if not decision.allowed:
        catalog.persist_quality_report(
            dataset_id,
            report,
            known_issues=issue_updates,
        )
        raise QuarantineError(
            f"dataset {dataset_id} quarantined: {decision.status.value}",
            dataset_id=dataset_id,
            status=decision.status,
        )
    catalog.persist_quality_report(
        dataset_id,
        report,
        known_issues=issue_updates,
    )
    return catalog.get_manifest(dataset_id)
