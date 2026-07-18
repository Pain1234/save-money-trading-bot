"""Evaluate regime-level quality metrics from a sealed research run (#287)."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

from research.artifacts import load_checksums, verify_checksums_against
from research.regime_quality.availability import NOT_AVAILABLE
from research.regime_quality.join import (
    attribute_equity,
    attribute_trades,
    index_day_labels,
)
from research.regime_quality.metrics import RegimeSliceRaw, compute_slice_metrics
from research.regime_quality.scoring import (
    compute_score_policy_content_hash,
    get_score_policy,
    summarize_slice_score,
)

REGIME_METRICS_SCHEMA_VERSION = "1.0"
REGIME_METRICS_FILENAME = "regime_metrics.json"


class RegimeQualityError(Exception):
    """Missing inputs, pin mismatch, or integrity failures."""


def _canonical_json_bytes(payload: object) -> bytes:
    return json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def compute_quality_id(
    *,
    run_id: str,
    dataset_id: str,
    dataset_content_hash: str,
    classification_id: str,
    classifier_content_hash: str,
    score_policy_version: str,
    score_policy_content_hash: str,
) -> str:
    digest = hashlib.sha256(
        _canonical_json_bytes(
            {
                "classification_id": classification_id,
                "classifier_content_hash": classifier_content_hash,
                "dataset_content_hash": dataset_content_hash,
                "dataset_id": dataset_id,
                "run_id": run_id,
                "score_policy_content_hash": score_policy_content_hash,
                "score_policy_version": score_policy_version,
            }
        )
    ).hexdigest()
    return f"rq_{digest}"


@dataclass(frozen=True)
class RegimeQualityResult:
    artifact: dict[str, Any]
    quality_id: str
    slices: tuple[RegimeSliceRaw, ...]


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _resolve_dataset_pins(
    regime_labels: Mapping[str, Any],
    *,
    dataset_id: str | None,
    dataset_content_hash: str | None,
) -> tuple[str, str]:
    """Prefer labels as source of truth; reject conflicting caller pins."""
    label_id = str(regime_labels.get("dataset_id") or "")
    label_hash = str(regime_labels.get("dataset_content_hash") or "")
    if not label_id or not label_hash:
        raise RegimeQualityError(
            "regime_labels.json missing dataset_id / dataset_content_hash pins"
        )
    if dataset_id is not None and dataset_id != label_id:
        raise RegimeQualityError(
            f"dataset_id pin mismatch: caller={dataset_id!r} labels={label_id!r}"
        )
    if dataset_content_hash is not None and dataset_content_hash != label_hash:
        raise RegimeQualityError(
            "dataset_content_hash pin mismatch: "
            f"caller={dataset_content_hash!r} labels={label_hash!r}"
        )
    return label_id, label_hash


def _pick_extreme(
    slices: list[RegimeSliceRaw],
    *,
    mode: str,
    evidence_status: str,
) -> dict[str, Any]:
    if evidence_status == "INCONCLUSIVE":
        return {
            "cell_id": NOT_AVAILABLE,
            "net_pnl": NOT_AVAILABLE,
            "reason": "inconclusive_coverage",
        }
    ranked = [s for s in slices if not s.zero_activity and s.status == "OK"]
    if not ranked:
        return {
            "cell_id": NOT_AVAILABLE,
            "net_pnl": NOT_AVAILABLE,
            "reason": "no_active_regimes",
        }
    chosen = (
        min(ranked, key=lambda s: s.net_pnl)
        if mode == "worst"
        else max(ranked, key=lambda s: s.net_pnl)
    )
    return {
        "cell_id": chosen.cell_id,
        "trend": chosen.trend,
        "vol": chosen.vol,
        "net_pnl": format(chosen.net_pnl, "f"),
        "gross_pnl": format(chosen.gross_pnl, "f"),
        "closed_trades": chosen.closed_trades,
    }


def evaluate_regime_quality(
    *,
    regime_labels: Mapping[str, Any],
    trades: list[Mapping[str, Any]],
    equity: list[Mapping[str, Any]],
    run_id: str,
    experiment_id: str,
    dataset_id: str | None = None,
    dataset_content_hash: str | None = None,
    score_policy_version: str = "1.0",
    benchmark_closes: Mapping[date, Decimal] | None = None,
) -> RegimeQualityResult:
    """Compute per-regime raw metrics + worst/strongest profile."""
    if regime_labels.get("point_in_time_safe") is True:
        raise RegimeQualityError(
            "refusing point_in_time_safe=true labels for ex-post quality join"
        )

    ds_id, ds_hash = _resolve_dataset_pins(
        regime_labels,
        dataset_id=dataset_id,
        dataset_content_hash=dataset_content_hash,
    )

    day_index = index_day_labels(regime_labels)
    trade_attr = attribute_trades(trades, day_index)
    equity_attr = attribute_equity(equity, day_index)

    closed_total = trade_attr.closed_total
    closed_labeled = trade_attr.closed_labeled
    coverage_ratio = (
        float(closed_labeled) / float(closed_total) if closed_total else 1.0
    )
    evidence_status = (
        "INCONCLUSIVE"
        if closed_total > 0 and closed_labeled < closed_total
        else "OK"
    )

    cell_ids = sorted(set(trade_attr.by_cell) | set(equity_attr.by_cell))
    for period in regime_labels.get("period_labels") or []:
        if not isinstance(period, dict):
            continue
        if period.get("status") != "OK":
            continue
        cell = f"{period.get('trend')}|{period.get('vol')}"
        if cell not in cell_ids:
            cell_ids.append(cell)
    cell_ids = sorted(set(cell_ids))

    slices: list[RegimeSliceRaw] = []
    for cell_id in cell_ids:
        slices.append(
            compute_slice_metrics(
                cell_id=cell_id,
                trades=trade_attr.by_cell.get(cell_id, []),
                equity=equity_attr.by_cell.get(cell_id, []),
                timeline=equity_attr.timeline,
                benchmark_closes=benchmark_closes,
            )
        )

    policy = get_score_policy(score_policy_version)
    policy_hash = compute_score_policy_content_hash(policy)
    classification_id = str(regime_labels.get("classification_id") or "")
    clf_hash = str(regime_labels.get("classifier_content_hash") or "")
    quality_id = compute_quality_id(
        run_id=run_id,
        dataset_id=ds_id,
        dataset_content_hash=ds_hash,
        classification_id=classification_id,
        classifier_content_hash=clf_hash,
        score_policy_version=policy.version,
        score_policy_content_hash=policy_hash,
    )

    regime_rows = []
    for sl in slices:
        row = sl.to_dict()
        row["quality_summary"] = summarize_slice_score(sl, policy=policy)
        regime_rows.append(row)

    attributed_net = trade_attr.attributed_net_pnl()
    source_net = trade_attr.source_net_pnl()
    excluded_net = trade_attr.excluded_net_pnl()
    port_gross = sum((s.gross_pnl for s in slices), Decimal("0"))
    port_fees = sum((s.fees for s in slices), Decimal("0"))
    port_slip = sum((s.slippage_costs for s in slices), Decimal("0"))
    port_fund = sum((s.funding_costs for s in slices), Decimal("0"))

    symbol_totals: dict[str, Decimal] = {}
    for sl in slices:
        for sym, pnl in sl.symbol_net_pnl.items():
            symbol_totals[sym] = symbol_totals.get(sym, Decimal("0")) + pnl

    artifact: dict[str, Any] = {
        "schema_version": REGIME_METRICS_SCHEMA_VERSION,
        "quality_id": quality_id,
        "experiment_id": experiment_id,
        "run_id": run_id,
        "dataset_id": ds_id,
        "dataset_content_hash": ds_hash,
        "classification_id": classification_id,
        "classifier_version": regime_labels.get("classifier_version"),
        "classifier_content_hash": clf_hash,
        "labeling_mode": regime_labels.get("labeling_mode"),
        "point_in_time_safe": False,
        "evidence_status": evidence_status,
        "attribution_rule": {
            "trades": "exit_time_utc_date",
            "equity": "time_utc_date",
            "drawdown": "contiguous_episode_rebased",
        },
        "coverage": {
            "closed_trades_total": closed_total,
            "closed_trades_labeled": closed_labeled,
            "closed_trades_unlabeled": len(trade_attr.unlabeled),
            "closed_trades_insufficient": len(trade_attr.insufficient),
            "open_or_missing_exit": len(trade_attr.open_or_missing_exit),
            "coverage_ratio": coverage_ratio,
            "equity_points_unlabeled": equity_attr.unlabeled_points,
            "equity_points_insufficient": equity_attr.insufficient_points,
        },
        "reconciliation": {
            "source_net_pnl": format(source_net, "f"),
            "attributed_net_pnl": format(attributed_net, "f"),
            "excluded_net_pnl": format(excluded_net, "f"),
            "balanced": source_net == attributed_net + excluded_net,
        },
        "score_policy_version": policy.version,
        "score_policy_content_hash": policy_hash,
        "decision_binding": False,
        "auto_promotion": False,
        "regimes": regime_rows,
        "portfolio": {
            "closed_trades_attributed": closed_labeled,
            "closed_trades_source": closed_total,
            "net_pnl_attributed": format(attributed_net, "f"),
            "net_pnl_source": format(source_net, "f"),
            "net_pnl_excluded": format(excluded_net, "f"),
            "gross_pnl_attributed": format(port_gross, "f"),
            "costs_attributed": {
                "fees": format(port_fees, "f"),
                "slippage_costs": format(port_slip, "f"),
                "funding_costs": format(port_fund, "f"),
            },
        },
        "symbols": {
            sym: format(pnl, "f") for sym, pnl in sorted(symbol_totals.items())
        },
        "worst_regime": _pick_extreme(
            slices, mode="worst", evidence_status=evidence_status
        ),
        "strongest_regime": _pick_extreme(
            slices, mode="strongest", evidence_status=evidence_status
        ),
    }
    return RegimeQualityResult(
        artifact=artifact, quality_id=quality_id, slices=tuple(slices)
    )


def evaluate_regime_quality_from_run_dir(
    run_dir: Path,
    *,
    score_policy_version: str = "1.0",
    trusted_checksums: Mapping[str, str] | None = None,
    benchmark_closes: Mapping[date, Decimal] | None = None,
) -> RegimeQualityResult:
    """Load sealed run artifacts, verify checksums, evaluate regime quality.

    Pin consistency: manifest and ``regime_labels.json`` dataset pins must match.
    Checksums: ``trusted_checksums`` (registry snapshot) if provided, else
    on-disk ``checksums.json`` (fail-closed if missing).
    """
    labels_path = run_dir / "regime_labels.json"
    trades_path = run_dir / "trades.json"
    equity_path = run_dir / "equity.json"
    manifest_path = run_dir / "run_manifest.json"
    for path in (labels_path, trades_path, equity_path, manifest_path):
        if not path.is_file():
            raise RegimeQualityError(f"missing required artifact: {path.name}")

    if trusted_checksums is not None:
        try:
            verify_checksums_against(run_dir, dict(trusted_checksums))
        except (ValueError, FileNotFoundError) as exc:
            raise RegimeQualityError(f"trusted checksum verify failed: {exc}") from exc
    else:
        checksums_path = run_dir / "checksums.json"
        if not checksums_path.is_file():
            raise RegimeQualityError(
                "checksums.json missing — refuse unsealed run evaluation"
            )
        try:
            verify_checksums_against(run_dir, load_checksums(run_dir))
        except (ValueError, FileNotFoundError) as exc:
            raise RegimeQualityError(f"checksum verify failed: {exc}") from exc

    labels = _load_json(labels_path)
    trades = _load_json(trades_path)
    equity = _load_json(equity_path)
    manifest = _load_json(manifest_path)
    if not isinstance(labels, dict):
        raise RegimeQualityError("regime_labels.json must be an object")
    if not isinstance(trades, list):
        raise RegimeQualityError("trades.json must be a list")
    if not isinstance(equity, list):
        raise RegimeQualityError("equity.json must be a list")
    if not isinstance(manifest, dict):
        raise RegimeQualityError("run_manifest.json must be an object")

    man_id = str(manifest.get("dataset_id") or "")
    man_hash = str(manifest.get("dataset_content_hash") or "")
    lab_id = str(labels.get("dataset_id") or "")
    lab_hash = str(labels.get("dataset_content_hash") or "")
    if man_id and lab_id and man_id != lab_id:
        raise RegimeQualityError(
            f"manifest/labels dataset_id mismatch: {man_id!r} vs {lab_id!r}"
        )
    if man_hash and lab_hash and man_hash != lab_hash:
        raise RegimeQualityError(
            "manifest/labels dataset_content_hash mismatch"
        )

    return evaluate_regime_quality(
        regime_labels=labels,
        trades=trades,
        equity=equity,
        run_id=str(manifest.get("run_id") or run_dir.name),
        experiment_id=str(manifest.get("experiment_id") or run_dir.parent.name),
        # Pins must match labels; pass manifest values for cross-check.
        dataset_id=lab_id or None,
        dataset_content_hash=lab_hash or None,
        score_policy_version=score_policy_version,
        benchmark_closes=benchmark_closes,
    )
