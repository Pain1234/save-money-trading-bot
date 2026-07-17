"""Versioned research metrics + benchmark contract (Issue #144 / P4-04)."""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from research.costs import SUPPORTED_COST_MODEL_VERSIONS

METRICS_SCHEMA_VERSION = "1.2"
# 1.0 = pre-funding_costs; 1.1 = funding identity (benchmark_result was gross);
# 1.2 = benchmark_result is net + required BenchmarkRef.gross_return/cost_model_version
SUPPORTED_METRICS_SCHEMA_VERSIONS: frozenset[str] = frozenset({"1.0", "1.1", "1.2"})
ReportStatus = Literal["complete", "incomplete", "invalid"]


def compute_gross_pnl(
    net_pnl: Decimal,
    fees: Decimal,
    slippage_costs: Decimal,
    funding_costs: Decimal,
) -> Decimal:
    """Gross PnL restores all cost components embedded in net.

    Identity: ``gross = net + fees + slippage + funding``.
    """
    return net_pnl + fees + slippage_costs + funding_costs


class BenchmarkRef(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    benchmark_id: str = Field(min_length=1)
    benchmark_version: str = Field(min_length=1)
    calculation: str = Field(
        min_length=1,
        description="Human/machine description of the benchmark algorithm",
    )
    period_parity: bool = True
    dataset_parity: bool = True
    cost_parity: bool = True
    # Versioned cost pin + gross/net (#208). gross_return is price-only;
    # net is carried as ResearchMetrics.benchmark_result.
    cost_model_version: str = Field(default="", description="Cost model applied for net")
    gross_return: Decimal | None = None


class ResearchMetrics(BaseModel):
    """Comparable research metrics export (metrics.json)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: str = Field(default=METRICS_SCHEMA_VERSION)
    status: ReportStatus = "complete"
    start_capital: Decimal
    end_capital: Decimal
    gross_pnl: Decimal
    net_pnl: Decimal
    fees: Decimal
    slippage_costs: Decimal
    funding_costs: Decimal = Decimal("0")
    funding_assumption: str
    signal_count: int = Field(ge=0)
    order_count: int = Field(ge=0)
    fill_count: int = Field(ge=0)
    closed_trades: int = Field(ge=0)
    hit_rate: Decimal | None = None
    avg_win: Decimal | None = None
    avg_loss: Decimal | None = None
    expectancy: Decimal | None = None
    profit_factor: Decimal | None = None
    max_drawdown: Decimal | None = None
    exposure: Decimal | None = None
    turnover: Decimal | None = None
    time_in_market: Decimal | None = None
    benchmark: BenchmarkRef
    benchmark_result: Decimal | None = None

    @model_validator(mode="after")
    def _costs_required_for_complete(self) -> ResearchMetrics:
        if self.schema_version not in SUPPORTED_METRICS_SCHEMA_VERSIONS:
            msg = (
                f"unsupported metrics schema_version {self.schema_version!r}; "
                f"supported={sorted(SUPPORTED_METRICS_SCHEMA_VERSIONS)}"
            )
            raise ValueError(msg)
        if self.status == "complete":
            # Fees/slippage may be zero but must be present (Decimal fields enforce).
            if self.funding_assumption.strip() == "":
                msg = "funding_assumption must be non-empty for complete metrics"
                raise ValueError(msg)
            if self.schema_version in {"1.2"}:
                if self.benchmark_result is None:
                    msg = "benchmark_result required for complete metrics schema 1.2+"
                    raise ValueError(msg)
                cost_ver = self.benchmark.cost_model_version.strip()
                if not cost_ver:
                    msg = (
                        "benchmark.cost_model_version required for complete "
                        "metrics schema 1.2+"
                    )
                    raise ValueError(msg)
                if cost_ver not in SUPPORTED_COST_MODEL_VERSIONS:
                    msg = (
                        "benchmark.cost_model_version "
                        f"{cost_ver!r} is not supported; "
                        f"supported={sorted(SUPPORTED_COST_MODEL_VERSIONS)}"
                    )
                    raise ValueError(msg)
                if self.benchmark.gross_return is None:
                    msg = (
                        "benchmark.gross_return required for complete "
                        "metrics schema 1.2+ (benchmark_result is net)"
                    )
                    raise ValueError(msg)
                # Loaded complete 1.2 artifacts must keep parity claims honest.
                if not self.benchmark.cost_parity:
                    msg = (
                        "benchmark.cost_parity must be true for complete "
                        "metrics schema 1.2+"
                    )
                    raise ValueError(msg)
                if not self.benchmark.period_parity:
                    msg = (
                        "benchmark.period_parity must be true for complete "
                        "metrics schema 1.2+"
                    )
                    raise ValueError(msg)
                if not self.benchmark.dataset_parity:
                    msg = (
                        "benchmark.dataset_parity must be true for complete "
                        "metrics schema 1.2+"
                    )
                    raise ValueError(msg)
            if self.schema_version in {"1.1", "1.2"}:
                # Gross must restore fees + slippage + funding (identity contract).
                expected = compute_gross_pnl(
                    self.net_pnl,
                    self.fees,
                    self.slippage_costs,
                    self.funding_costs,
                )
                if self.gross_pnl != expected:
                    msg = (
                        "gross_pnl must equal net_pnl + fees + slippage_costs "
                        "+ funding_costs for schema 1.1+"
                    )
                    raise ValueError(msg)
        return self


def parse_benchmark_ref(benchmark_field: str) -> BenchmarkRef:
    """Parse Spec.benchmark string into a versioned BenchmarkRef.

    Accepted forms:
    - ``buy_and_hold_BTC`` → id=buy_and_hold_BTC, version=1.0
    - ``id@version`` → explicit version
    """
    text = benchmark_field.strip()
    if not text:
        msg = "benchmark is required"
        raise ValueError(msg)
    if "@" in text:
        bid, ver = text.split("@", 1)
        if not bid or not ver:
            msg = "benchmark must be 'id@version' or a non-empty id"
            raise ValueError(msg)
        return BenchmarkRef(
            benchmark_id=bid,
            benchmark_version=ver,
            calculation=f"declared benchmark {bid}@{ver}",
        )
    return BenchmarkRef(
        benchmark_id=text,
        benchmark_version="1.0",
        calculation=f"declared benchmark {text}@1.0 (buy-and-hold style unless overridden)",
    )


def validate_metrics_or_mark_invalid(data: dict[str, Any]) -> ResearchMetrics:
    """Validate metrics payload; missing/incompatible data → incomplete/invalid."""
    try:
        metrics = ResearchMetrics.model_validate(data)
    except Exception as exc:  # noqa: BLE001 — map to invalid contract status
        raise ValueError(f"metrics schema/run validation failed: {exc}") from exc
    if metrics.benchmark.benchmark_id.strip() == "":
        msg = "benchmark_id missing; report remains incomplete/invalid"
        raise ValueError(msg)
    return metrics


def metrics_to_canonical_dict(metrics: ResearchMetrics) -> dict[str, Any]:
    raw = metrics.model_dump(mode="python")

    def _enc(value: Any) -> Any:
        if isinstance(value, Decimal):
            return format(value, "f")
        if isinstance(value, dict):
            return {str(k): _enc(v) for k, v in sorted(value.items())}
        if isinstance(value, list):
            return [_enc(v) for v in value]
        return value

    encoded = _enc(raw)
    assert isinstance(encoded, dict)
    return encoded


def dumps_metrics(metrics: ResearchMetrics) -> bytes:
    return (
        json.dumps(
            metrics_to_canonical_dict(metrics),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
        + b"\n"
    )


def render_report_md(metrics: ResearchMetrics) -> str:
    """Static report.md consistent with metrics.json."""
    b = metrics.benchmark
    lines = [
        f"# Research report ({metrics.status})",
        "",
        f"- schema_version: `{metrics.schema_version}`",
        f"- start_capital: `{metrics.start_capital}`",
        f"- end_capital: `{metrics.end_capital}`",
        f"- gross_pnl: `{metrics.gross_pnl}`",
        f"- net_pnl: `{metrics.net_pnl}`",
        f"- fees: `{metrics.fees}`",
        f"- slippage_costs: `{metrics.slippage_costs}`",
        f"- funding_costs: `{metrics.funding_costs}`",
        f"- funding_assumption: `{metrics.funding_assumption}`",
        f"- closed_trades: `{metrics.closed_trades}`",
        f"- hit_rate: `{metrics.hit_rate}`",
        f"- profit_factor: `{metrics.profit_factor}`",
        f"- max_drawdown: `{metrics.max_drawdown}`",
        (
            f"- benchmark: `{b.benchmark_id}@{b.benchmark_version}` "
            f"(period_parity={b.period_parity}, dataset_parity={b.dataset_parity}, "
            f"cost_parity={b.cost_parity}, cost_model_version={b.cost_model_version})"
        ),
        f"- benchmark_gross_return: `{b.gross_return}`",
        f"- benchmark_result (net): `{metrics.benchmark_result}`",
        f"- calculation: {b.calculation}",
        "",
    ]
    return "\n".join(lines)


def save_metrics_and_report(
    metrics: ResearchMetrics,
    metrics_path: str | Path,
    report_path: str | Path,
) -> None:
    metrics_file = Path(metrics_path)
    report_file = Path(report_path)
    metrics_file.parent.mkdir(parents=True, exist_ok=True)
    report_file.parent.mkdir(parents=True, exist_ok=True)
    metrics_file.write_bytes(dumps_metrics(metrics))
    report_file.write_text(render_report_md(metrics), encoding="utf-8")
