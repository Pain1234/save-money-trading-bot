"""Evidence inputs and limitation blocks for confidence evaluation (#288)."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any


@dataclass(frozen=True)
class ConfidenceEvidenceInputs:
    """Measurable inputs only — no free-form manual confidence override."""

    run_id: str
    experiment_id: str
    dataset_id: str
    dataset_content_hash: str
    run_status: str

    closed_trades: int | None = None
    equity_periods: int | None = None

    walk_forward_folds_complete: int | None = None
    walk_forward_fold_pass_ratio: Decimal | None = None
    parameter_neighbors_complete: int | None = None
    parameter_neighbor_pass_ratio: Decimal | None = None

    # When bootstrap was assessed: usable series length (equity periods) and block length.
    bootstrap_series_length: int | None = None
    bootstrap_block_length: int | None = None
    bootstrap_assessed: bool = False

    regime_coverage_ratio: Decimal | None = None
    regime_evidence_status: str | None = None

    gate_integrity_status: str | None = None
    robustness_run_ids: tuple[str, ...] = ()
    gate_run_id: str | None = None

    # Optional caller-supplied multiple-testing metadata (never invented).
    multiple_testing_metadata: Mapping[str, Any] | None = None


@dataclass(frozen=True)
class ConfidenceLimitation:
    """Visible process limitation (serial dependence, multiple testing, …)."""

    code: str
    status: str
    detail: str
    raw: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "code": self.code,
            "detail": self.detail,
            "status": self.status,
        }
        if self.raw:
            payload["raw"] = dict(self.raw)
        return payload


def build_limitations(inputs: ConfidenceEvidenceInputs) -> tuple[ConfidenceLimitation, ...]:
    """Always emit serial-dependence and multiple-testing visibility (#288 ACs)."""
    limitations: list[ConfidenceLimitation] = []

    if inputs.bootstrap_assessed and inputs.bootstrap_series_length is not None:
        limitations.append(
            ConfidenceLimitation(
                code="serial_dependence",
                status="ASSESSED_VIA_BLOCK_BOOTSTRAP",
                detail=(
                    "Block bootstrap inputs present; confidence uses series length "
                    "relative to block_length as a serial-dependence-aware proxy. "
                    "Full PSR/DSR/PBO/MTRL deferred."
                ),
                raw={
                    "bootstrap_block_length": inputs.bootstrap_block_length,
                    "bootstrap_series_length": inputs.bootstrap_series_length,
                },
            )
        )
    else:
        limitations.append(
            ConfidenceLimitation(
                code="serial_dependence",
                status="LIMITATION",
                detail=(
                    "Block-bootstrap serial-dependence assessment not available; "
                    "dimension bootstrap_uncertainty is NOT_AVAILABLE and must not "
                    "be treated as PASS/HIGH by omission."
                ),
            )
        )

    if inputs.multiple_testing_metadata is not None:
        limitations.append(
            ConfidenceLimitation(
                code="multiple_testing",
                status="DOCUMENTED",
                detail="Caller-supplied multiple-testing metadata attached.",
                raw=dict(inputs.multiple_testing_metadata),
            )
        )
    else:
        limitations.append(
            ConfidenceLimitation(
                code="multiple_testing",
                status="LIMITATION",
                detail=(
                    "Number of variants tested / multiple-testing adjustment not "
                    "documented for this profile; do not interpret confidence as "
                    "multiple-testing-corrected. PSR/DSR/PBO deferred."
                ),
                raw={"variants_tested": None},
            )
        )

    if inputs.gate_integrity_status and inputs.gate_integrity_status != "VALID":
        limitations.append(
            ConfidenceLimitation(
                code="integrity_context",
                status="LIMITATION",
                detail=(
                    f"gate_integrity_status={inputs.gate_integrity_status!r}; "
                    "trusted quality scoring remains blocked per #286."
                ),
            )
        )

    return tuple(limitations)
