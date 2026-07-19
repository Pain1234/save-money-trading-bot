"""Read-only scorecard detail assembler (#350).

Joins sealed Layer-1..4 artifacts already bound on a :class:`ScorecardRecord`
into per-regime table rows and forensic drilldowns for the dashboard.

This module does **not** re-score regimes, re-open promotion, or invent
missing metrics. Absent evidence is surfaced as ``NOT_AVAILABLE``.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from research.gate_evaluator import GateResultStore
from research.registry import ExperimentRegistry
from research.robustness import load_robustness_manifest
from research.scorecard_evaluator import (
    ScorecardEvaluationError,
    ScorecardRecord,
    verify_scorecard_record_artifact_checksums,
)

NOT_AVAILABLE = "NOT_AVAILABLE"

_LAYER_FILES = (
    "regime_labels.json",
    "regime_metrics.json",
    "behavior_profile.json",
    "confidence_profile.json",
    "parameter_area.json",
)


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeError):
        return None
    return raw if isinstance(raw, dict) else None


def _is_missing(value: Any) -> bool:
    return value is None or value == NOT_AVAILABLE


def _na_metric() -> dict[str, Any]:
    return {"status": NOT_AVAILABLE, "value": None}


def _metric(value: Any) -> dict[str, Any]:
    if _is_missing(value):
        return _na_metric()
    return {"status": "OK", "value": value}


def _quality_from_row(row: dict[str, Any]) -> dict[str, Any]:
    summary = row.get("quality_summary")
    if not isinstance(summary, dict):
        return _na_metric()
    score = summary.get("score")
    if _is_missing(score):
        return {
            "status": NOT_AVAILABLE,
            "value": None,
            "reason": summary.get("reason"),
            "score_policy_content_hash": summary.get("score_policy_content_hash"),
        }
    return {
        "status": "OK",
        "value": score,
        "reason": summary.get("reason"),
        "score_policy_content_hash": summary.get("score_policy_content_hash"),
    }


def _index_behaviour(behavior: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    if not isinstance(behavior, dict):
        return out
    for item in behavior.get("regimes") or []:
        if not isinstance(item, dict):
            continue
        cell_id = str(item.get("cell_id") or "").strip()
        if cell_id:
            out[cell_id] = item
    return out


def _behaviour_cell(row: dict[str, Any] | None) -> dict[str, Any]:
    if row is None:
        return {
            "status": NOT_AVAILABLE,
            "main_weakness": NOT_AVAILABLE,
            "main_strength": NOT_AVAILABLE,
            "labels": [],
        }
    weakness = row.get("main_weakness")
    strength = row.get("main_strength")
    labels = list(row.get("labels") or [])
    if _is_missing(weakness) and _is_missing(strength) and not labels:
        return {
            "status": NOT_AVAILABLE,
            "main_weakness": NOT_AVAILABLE,
            "main_strength": NOT_AVAILABLE,
            "labels": [],
        }
    return {
        "status": "OK",
        "main_weakness": weakness if not _is_missing(weakness) else NOT_AVAILABLE,
        "main_strength": strength if not _is_missing(strength) else NOT_AVAILABLE,
        "labels": labels,
        "closed_trades": row.get("closed_trades"),
        "net_pnl": row.get("net_pnl"),
    }


def _confidence_overall(global_profile: dict[str, Any]) -> str | None:
    conf = global_profile.get("confidence")
    if isinstance(conf, dict):
        label = conf.get("overall_label")
        if isinstance(label, str) and label.strip() and label != NOT_AVAILABLE:
            return label
    return None


def _build_regime_rows(
    *,
    metrics: dict[str, Any] | None,
    behavior: dict[str, Any] | None,
    confidence_overall: str | None,
) -> list[dict[str, Any]]:
    rows_out: list[dict[str, Any]] = []
    if not isinstance(metrics, dict):
        return rows_out
    behaviour_by_cell = _index_behaviour(behavior)
    conf_status = "OK" if confidence_overall else NOT_AVAILABLE
    conf_value = confidence_overall if confidence_overall else None

    for row in metrics.get("regimes") or []:
        if not isinstance(row, dict):
            continue
        cell_id = str(row.get("cell_id") or "").strip()
        if not cell_id:
            continue
        rows_out.append(
            {
                "cell_id": cell_id,
                "trend": row.get("trend"),
                "vol": row.get("vol"),
                "quality": _quality_from_row(row),
                "confidence": {
                    "status": conf_status,
                    "value": conf_value,
                    "scope": "scorecard_overall",
                },
                "behaviour": _behaviour_cell(behaviour_by_cell.get(cell_id)),
                "trades": _metric(row.get("closed_trades")),
                "net_pnl": _metric(row.get("net_pnl")),
                "max_drawdown": _metric(row.get("max_drawdown")),
                "costs": _metric(row.get("costs")),
                "benchmark_delta": _metric(row.get("benchmark_delta")),
                "row_status": row.get("status"),
            }
        )
    return rows_out


def _transition_risk(
    *,
    behavior: dict[str, Any] | None,
    global_profile: dict[str, Any],
) -> dict[str, Any]:
    value = None
    if isinstance(behavior, dict):
        value = behavior.get("transition_risk")
    if value is None:
        beh = global_profile.get("behaviour")
        if isinstance(beh, dict):
            value = beh.get("transition_risk")
    if value is None:
        return _na_metric()
    return {"status": "OK", "value": value}


def _cost_stress_from_pinned(
    root: Path,
    record: ScorecardRecord,
) -> dict[str, Any]:
    """Surface pinned cost-stress robustness summary; never invent scenarios."""
    for rid in record.robustness_run_ids:
        manifest = load_robustness_manifest(root, rid)
        if not isinstance(manifest, dict):
            continue
        if str(manifest.get("test_type") or "") != "cost_stress":
            continue
        children = manifest.get("children")
        elevated: dict[str, Any] | None = None
        if isinstance(children, list):
            for child in children:
                if not isinstance(child, dict):
                    continue
                label = str(child.get("label") or child.get("child_id") or "")
                if "combined_elevated" in label:
                    elevated = child
                    break
        return {
            "status": "OK",
            "robustness_run_id": rid,
            "verdict": manifest.get("verdict"),
            "summary": manifest.get("summary"),
            "combined_elevated_child": elevated,
            "artifact_path": f"robustness/{rid}/manifest.json",
        }
    return {
        "status": NOT_AVAILABLE,
        "value": None,
        "reason": "no_pinned_cost_stress_robustness_run",
    }


def _gate_failures(root: Path, gate_run_id: str | None) -> list[dict[str, Any]]:
    if not gate_run_id:
        return [
            {
                "status": NOT_AVAILABLE,
                "reason": "no_bound_gate_run",
            }
        ]
    gate = GateResultStore(root).get(gate_run_id)
    if gate is None:
        return [
            {
                "status": NOT_AVAILABLE,
                "reason": "gate_run_unreadable",
                "gate_run_id": gate_run_id,
            }
        ]
    failures: list[dict[str, Any]] = []
    for g in gate.gates:
        if g.outcome == "PASS":
            continue
        failures.append(
            {
                "name": g.name,
                "outcome": g.outcome,
                "passed": g.passed,
                "threshold": g.threshold,
                "measured_value": g.measured_value,
                "reason": g.reason,
                "category": g.category,
            }
        )
    return failures


def _raw_artifact_refs(
    root: Path,
    record: ScorecardRecord,
    *,
    run_dir: Path | None,
) -> list[dict[str, Any]]:
    refs: list[dict[str, Any]] = []
    for name in _LAYER_FILES:
        checksum = record.artifact_checksums.get(name)
        path = (run_dir / name) if run_dir is not None else None
        refs.append(
            {
                "name": name,
                "relative_path": name,
                "checksum_sha256": checksum,
                "present": bool(path is not None and path.is_file()),
                "status": "OK" if checksum else NOT_AVAILABLE,
            }
        )
    for key, digest in sorted(record.artifact_checksums.items()):
        if key in _LAYER_FILES:
            continue
        refs.append(
            {
                "name": key,
                "relative_path": key,
                "checksum_sha256": digest,
                "present": True,
                "status": "OK",
            }
        )
    self_key = f"scorecard/{record.scorecard_id}.json"
    refs.append(
        {
            "name": "scorecard_record",
            "relative_path": f"scorecards/{record.scorecard_id}.json",
            "checksum_sha256": record.artifact_checksums.get(self_key),
            "present": (root / "scorecards" / f"{record.scorecard_id}.json").is_file()
            or (root / "scorecards" / "registry.jsonl").is_file(),
            "status": "OK",
        }
    )
    return refs


def _profile_section(global_profile: dict[str, Any], key: str) -> dict[str, Any]:
    raw = global_profile.get(key)
    return raw if isinstance(raw, dict) else {}


def _evidence_inputs(record: ScorecardRecord, global_profile: dict[str, Any]) -> dict[str, Any]:
    conf = _profile_section(global_profile, "confidence")
    beh = _profile_section(global_profile, "behaviour")
    gates = _profile_section(global_profile, "gates")
    quality = _profile_section(global_profile, "quality")
    return {
        "run_id": record.run_id,
        "experiment_id": record.experiment_id,
        "gate_run_id": record.gate_run_id,
        "robustness_run_ids": list(record.robustness_run_ids),
        "policy_version": record.policy_version,
        "policy_content_hash": record.policy_content_hash,
        "evidence_content_hash": record.evidence_content_hash,
        "dataset_id": record.dataset_id,
        "dataset_content_hash": record.dataset_content_hash,
        "run_code_commit": record.run_code_commit,
        "evaluation_code_commit": record.evaluation_code_commit,
        "evaluated_at": record.evaluated_at,
        "status": record.status,
        "invalidation_reason": record.invalidation_reason,
        "decision_binding": record.decision_binding,
        "auto_promotion": record.auto_promotion,
        "promotion_action": record.promotion_action,
        "global_profile_summary": {
            "confidence_overall": conf.get("overall_label"),
            "confidence_source": conf.get("source"),
            "main_strength": beh.get("main_strength"),
            "main_weakness": beh.get("main_weakness"),
            "transition_risk_present": beh.get("transition_risk") is not None,
            "parameter_area": global_profile.get("parameter_area"),
            "strongest_regime": quality.get("strongest_regime"),
            "worst_regime": quality.get("worst_regime"),
            "gate_overall_status": gates.get("overall_status"),
            "gate_integrity_status": gates.get("integrity_status"),
        },
        "layer_refs": dict(record.layer_refs),
        "layer_artifact_keys": sorted(
            k
            for k in record.artifact_checksums
            if k.endswith(".json") and not k.startswith("scorecard/")
        ),
    }


def assemble_scorecard_detail(root: Path, record: ScorecardRecord) -> dict[str, Any]:
    """Build the read-only detail payload for ``GET .../scorecards/{id}/detail``.

    Re-verifies bound seals before joining. Does not mutate the store.
    """
    verify_scorecard_record_artifact_checksums(root, record)

    registry = ExperimentRegistry(root.resolve())
    try:
        entry = registry.show(record.run_id, verify=True)
    except (KeyError, ValueError, FileNotFoundError) as exc:
        raise ScorecardEvaluationError(
            f"scorecard detail cannot open run_id={record.run_id}: {exc}",
            field_errors={"run_id": "unreadable"},
        ) from exc

    run_dir = Path(entry.artifact_path)
    metrics = _read_json(run_dir / "regime_metrics.json")
    behavior = _read_json(run_dir / "behavior_profile.json")
    global_profile = dict(record.global_profile)

    regime_rows = _build_regime_rows(
        metrics=metrics,
        behavior=behavior,
        confidence_overall=_confidence_overall(global_profile),
    )

    return {
        "scorecard_id": record.scorecard_id,
        "status": record.status,
        "decision_binding": record.decision_binding,
        "auto_promotion": record.auto_promotion,
        "promotion_action": record.promotion_action,
        "summary": record.to_dict(),
        "regime_rows": regime_rows,
        "transition_risk": _transition_risk(
            behavior=behavior, global_profile=global_profile
        ),
        "cost_stress": _cost_stress_from_pinned(root, record),
        "evidence_inputs": _evidence_inputs(record, global_profile),
        "gate_failures": _gate_failures(root, record.gate_run_id),
        "raw_artifact_refs": _raw_artifact_refs(root, record, run_dir=run_dir),
        "missing_data_semantics": {
            "token": NOT_AVAILABLE,
            "rule": (
                "Missing sealed evidence is returned as NOT_AVAILABLE; "
                "clients must not coerce to 0, PASS, or invent metrics."
            ),
        },
    }


__all__ = [
    "NOT_AVAILABLE",
    "assemble_scorecard_detail",
]
