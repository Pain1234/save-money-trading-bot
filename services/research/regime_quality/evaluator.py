"""Evaluate regime-level quality metrics from a sealed research run (#287)."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any

from research.regime_quality.availability import NOT_AVAILABLE
from research.regime_quality.join import (
    attribute_equity,
    attribute_trades,
    index_day_labels,
)
from research.regime_quality.metrics import RegimeSliceRaw, compute_slice_metrics
from research.regime_quality.scoring import (
    get_score_policy,
    summarize_slice_score,
)

REGIME_METRICS_SCHEMA_VERSION = "1.0"
REGIME_METRICS_FILENAME = "regime_metrics.json"


class RegimeQualityError(Exception):
    """Missing inputs or integrity failures for regime quality evaluation."""


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


def _pick_extreme(
    slices: list[RegimeSliceRaw],
    *,
    mode: str,
) -> dict[str, Any]:
    """Worst = lowest net_pnl; strongest = highest. Skip zero-activity for rank."""
    ranked = [s for s in slices if not s.zero_activity and s.status == "OK"]
    if not ranked:
        return {
            "cell_id": NOT_AVAILABLE,
            "net_pnl": NOT_AVAILABLE,
            "reason": "no_active_regimes",
        }
    if mode == "worst":
        chosen = min(ranked, key=lambda s: s.net_pnl)
    else:
        chosen = max(ranked, key=lambda s: s.net_pnl)
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
) -> RegimeQualityResult:
    """Compute per-regime raw metrics + worst/strongest profile."""
    if regime_labels.get("point_in_time_safe") is True:
        raise RegimeQualityError(
            "refusing point_in_time_safe=true labels for ex-post quality join"
        )

    day_index = index_day_labels(regime_labels)
    trade_buckets = attribute_trades(trades, day_index)
    equity_buckets = attribute_equity(equity, day_index)

    cell_ids = sorted(set(trade_buckets) | set(equity_buckets))
    # Also include cells present only in period_labels with OK status and no activity.
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
                trades=trade_buckets.get(cell_id, []),
                equity=equity_buckets.get(cell_id, []),
                benchmark_delta=NOT_AVAILABLE,  # optional; filled when series supplied
            )
        )

    policy = get_score_policy(score_policy_version)
    from research.regime_quality.scoring import compute_score_policy_content_hash

    policy_hash = compute_score_policy_content_hash(policy)
    ds_id = dataset_id or str(regime_labels.get("dataset_id") or "")
    ds_hash = dataset_content_hash or str(
        regime_labels.get("dataset_content_hash") or ""
    )
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

    # Portfolio view: sum active slices (raw, not score).
    port_net = sum((s.net_pnl for s in slices), Decimal("0"))
    port_gross = sum((s.gross_pnl for s in slices), Decimal("0"))
    port_fees = sum((s.fees for s in slices), Decimal("0"))
    port_slip = sum((s.slippage_costs for s in slices), Decimal("0"))
    port_fund = sum((s.funding_costs for s in slices), Decimal("0"))
    port_trades = sum(s.closed_trades for s in slices)

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
        "attribution_rule": {
            "trades": "exit_time_utc_date",
            "equity": "time_utc_date",
        },
        "score_policy_version": policy.version,
        "score_policy_content_hash": policy_hash,
        "decision_binding": False,
        "auto_promotion": False,
        "regimes": regime_rows,
        "portfolio": {
            "closed_trades": port_trades,
            "net_pnl": format(port_net, "f"),
            "gross_pnl": format(port_gross, "f"),
            "costs": {
                "fees": format(port_fees, "f"),
                "slippage_costs": format(port_slip, "f"),
                "funding_costs": format(port_fund, "f"),
            },
        },
        "symbols": {
            sym: format(pnl, "f") for sym, pnl in sorted(symbol_totals.items())
        },
        "worst_regime": _pick_extreme(slices, mode="worst"),
        "strongest_regime": _pick_extreme(slices, mode="strongest"),
    }
    return RegimeQualityResult(
        artifact=artifact, quality_id=quality_id, slices=tuple(slices)
    )


def evaluate_regime_quality_from_run_dir(
    run_dir: Path,
    *,
    score_policy_version: str = "1.0",
) -> RegimeQualityResult:
    """Load sealed run artifacts and evaluate regime quality."""
    labels_path = run_dir / "regime_labels.json"
    trades_path = run_dir / "trades.json"
    equity_path = run_dir / "equity.json"
    manifest_path = run_dir / "run_manifest.json"
    for path in (labels_path, trades_path, equity_path, manifest_path):
        if not path.is_file():
            raise RegimeQualityError(f"missing required artifact: {path.name}")

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

    return evaluate_regime_quality(
        regime_labels=labels,
        trades=trades,
        equity=equity,
        run_id=str(manifest.get("run_id") or run_dir.name),
        experiment_id=str(manifest.get("experiment_id") or run_dir.parent.name),
        dataset_id=str(
            manifest.get("dataset_id") or labels.get("dataset_id") or ""
        ),
        dataset_content_hash=str(
            manifest.get("dataset_content_hash")
            or labels.get("dataset_content_hash")
            or ""
        ),
        score_policy_version=score_policy_version,
    )
