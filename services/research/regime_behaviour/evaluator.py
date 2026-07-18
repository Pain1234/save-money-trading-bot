"""Build ``behavior_profile.json`` from regime metrics + labels (#289)."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from research.artifacts import verify_checksums_against
from research.regime_behaviour.labels import (
    derive_regime_labels,
    pick_main_strength,
    pick_main_weakness,
)
from research.regime_behaviour.policy import (
    BehaviourPolicyError,
    compute_policy_content_hash,
    get_behaviour_policy,
)
from research.regime_behaviour.transitions import build_transition_risk_profile

BEHAVIOUR_PROFILE_SCHEMA_VERSION = "1.0"
BEHAVIOUR_PROFILE_FILENAME = "behavior_profile.json"


class BehaviourProfileError(Exception):
    """Missing inputs, pin mismatch, or integrity failures."""


def _canonical_json_bytes(payload: object) -> bytes:
    return json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


_TRANSITION_TRADE_KEYS: tuple[str, ...] = (
    "entry_fill_price",
    "exit_time",
    "fees",
    "funding",
    "net_pnl",
    "quantity",
    "slippage_cost",
)


def _trade_evidence_rows(
    trades: Sequence[Mapping[str, Any]] | None,
) -> list[dict[str, object]]:
    """Normalize trade fields that affect transition_risk into identity rows."""
    rows: list[dict[str, object]] = []
    for trade in trades or ():
        rows.append({key: trade.get(key) for key in _TRANSITION_TRADE_KEYS})
    return rows


def compute_transition_evidence_hash(
    *,
    transitions: Sequence[Mapping[str, Any]],
    day_events: Sequence[Mapping[str, Any]],
    trades: Sequence[Mapping[str, Any]] | None = None,
) -> str:
    """Bind transition, day-event, and trade evidence into behaviour identity.

    Trade rows matter: ``transition_risk`` (window PnL / costs / turnover /
    HIGH vs MODERATE) is derived from trades exiting on TRANSITION_IN/OUT days.
    """
    return hashlib.sha256(
        _canonical_json_bytes(
            {
                "day_events": list(day_events),
                "trades": _trade_evidence_rows(trades),
                "transitions": list(transitions),
            }
        )
    ).hexdigest()


def compute_behaviour_id(
    *,
    run_id: str,
    quality_id: str,
    classification_id: str,
    classifier_content_hash: str,
    transition_evidence_hash: str,
    policy_version: str,
    policy_content_hash: str,
) -> str:
    digest = hashlib.sha256(
        _canonical_json_bytes(
            {
                "classification_id": classification_id,
                "classifier_content_hash": classifier_content_hash,
                "policy_content_hash": policy_content_hash,
                "policy_version": policy_version,
                "quality_id": quality_id,
                "run_id": run_id,
                "transition_evidence_hash": transition_evidence_hash,
            }
        )
    ).hexdigest()
    return f"bh_{digest}"


@dataclass(frozen=True)
class BehaviourProfileResult:
    artifact: dict[str, Any]
    behaviour_id: str


def _require_pin(source: Mapping[str, Any], key: str, *, label: str) -> str:
    value = str(source.get(key) or "")
    if not value:
        raise BehaviourProfileError(f"{label} missing required pin {key!r}")
    return value


def evaluate_behaviour_profile(
    *,
    regime_metrics: Mapping[str, Any],
    regime_labels: Mapping[str, Any] | None = None,
    trades: Sequence[Mapping[str, Any]] | None = None,
    policy_version: str = "1.0",
) -> BehaviourProfileResult:
    """Derive deterministic behaviour + transition-risk labels.

    No LLM. Persisted labels come only from versioned rules over raw metrics.
    Incomplete / INCONCLUSIVE quality evidence cannot yield positive strengths.
    """
    if regime_metrics.get("decision_binding") is True:
        raise BehaviourProfileError(
            "refusing decision_binding=true regime_metrics as behaviour input"
        )

    policy = get_behaviour_policy(policy_version)
    policy_hash = compute_policy_content_hash(policy)
    run_id = _require_pin(regime_metrics, "run_id", label="regime_metrics")
    quality_id = _require_pin(regime_metrics, "quality_id", label="regime_metrics")
    classification_id = _require_pin(
        regime_metrics, "classification_id", label="regime_metrics"
    )
    classifier_content_hash = _require_pin(
        regime_metrics, "classifier_content_hash", label="regime_metrics"
    )
    dataset_id = _require_pin(regime_metrics, "dataset_id", label="regime_metrics")
    dataset_content_hash = _require_pin(
        regime_metrics, "dataset_content_hash", label="regime_metrics"
    )

    # Pin consistency with labels when provided (dataset + classification).
    # Both sides required and must match exactly (no empty-left skip).
    if regime_labels is not None:
        for key in (
            "dataset_id",
            "dataset_content_hash",
            "classification_id",
            "classifier_content_hash",
        ):
            left = _require_pin(regime_metrics, key, label="regime_metrics")
            right = _require_pin(regime_labels, key, label="regime_labels")
            if left != right:
                raise BehaviourProfileError(
                    f"pin mismatch on {key}: metrics={left!r} labels={right!r}"
                )

    # Only explicit evidence_status == "OK" is trusted; missing/unknown fail closed.
    raw_evidence = regime_metrics.get("evidence_status")
    if raw_evidence is None or str(raw_evidence).strip() == "":
        evidence = "MISSING"
        evidence_trusted = False
    else:
        evidence = str(raw_evidence)
        evidence_trusted = evidence == "OK"

    regimes_out: list[dict[str, Any]] = []
    all_weaknesses: list[str] = []
    all_strengths: list[str] = []
    for row in regime_metrics.get("regimes") or []:
        if not isinstance(row, dict):
            continue
        labels = derive_regime_labels(
            row, policy, evidence_trusted=evidence_trusted
        )
        weakness = pick_main_weakness(labels, policy.weakness_priority)
        strength = (
            None
            if not evidence_trusted
            else pick_main_strength(labels, policy.strength_priority)
        )
        if weakness:
            all_weaknesses.append(weakness)
        if strength:
            all_strengths.append(strength)
        regimes_out.append(
            {
                "cell_id": row.get("cell_id"),
                "trend": row.get("trend"),
                "vol": row.get("vol"),
                "labels": list(labels),
                "main_weakness": weakness,
                "main_strength": strength,
                "zero_activity": row.get("zero_activity"),
                "closed_trades": row.get("closed_trades"),
                "net_pnl": row.get("net_pnl"),
            }
        )

    transitions: list[Mapping[str, Any]] = []
    day_events: list[Mapping[str, Any]] = []
    if regime_labels is not None:
        transitions = list(regime_labels.get("transitions") or [])
        day_events = list(regime_labels.get("day_events") or [])
    trade_list = list(trades) if trades else []
    transition_evidence_hash = compute_transition_evidence_hash(
        transitions=transitions,
        day_events=day_events,
        trades=trade_list,
    )
    transition_risk = build_transition_risk_profile(
        transitions=transitions,
        day_events=day_events,
        trades=trade_list or None,
        policy=policy,
        evidence_trusted=evidence_trusted,
    )

    behaviour_id = compute_behaviour_id(
        run_id=run_id,
        quality_id=quality_id,
        classification_id=classification_id,
        classifier_content_hash=classifier_content_hash,
        transition_evidence_hash=transition_evidence_hash,
        policy_version=policy.version,
        policy_content_hash=policy_hash,
    )

    global_weakness = None
    for candidate in policy.weakness_priority:
        if candidate in all_weaknesses:
            global_weakness = candidate
            break
    if not evidence_trusted:
        global_weakness = "INSUFFICIENT_EVIDENCE"
        global_strength = None
    else:
        global_strength = None
        for candidate in policy.strength_priority:
            if candidate in all_strengths:
                global_strength = candidate
                break

    artifact: dict[str, Any] = {
        "schema_version": BEHAVIOUR_PROFILE_SCHEMA_VERSION,
        "behaviour_id": behaviour_id,
        "experiment_id": regime_metrics.get("experiment_id"),
        "run_id": run_id,
        "quality_id": quality_id,
        "classification_id": classification_id,
        "classifier_content_hash": classifier_content_hash,
        "dataset_id": dataset_id,
        "dataset_content_hash": dataset_content_hash,
        "transition_evidence_hash": transition_evidence_hash,
        "policy_version": policy.version,
        "policy_content_hash": policy_hash,
        "llm_source": False,
        "decision_binding": False,
        "auto_promotion": False,
        "evidence_status": evidence,
        "evidence_trusted": evidence_trusted,
        "regimes": regimes_out,
        "transition_risk": transition_risk,
        "main_weakness": global_weakness,
        "main_strength": global_strength,
        "human_readable_summary": None,  # optional; never persisted as label source
    }
    return BehaviourProfileResult(artifact=artifact, behaviour_id=behaviour_id)


def evaluate_behaviour_profile_from_run_dir(
    run_dir: Path,
    *,
    policy_version: str = "1.0",
    trusted_checksums: Mapping[str, str],
) -> BehaviourProfileResult:
    """Load sealed run artifacts and evaluate behaviour.

    ``trusted_checksums`` is required (registry / external trust anchor).
    Local mutable ``checksums.json`` alone is not accepted as evidence trust.
    """
    metrics_path = run_dir / "regime_metrics.json"
    labels_path = run_dir / "regime_labels.json"
    trades_path = run_dir / "trades.json"
    if not metrics_path.is_file():
        raise BehaviourProfileError("missing regime_metrics.json")
    if not trusted_checksums:
        raise BehaviourProfileError(
            "trusted_checksums required — refuse evaluation without "
            "external registry trust anchor"
        )

    try:
        verify_checksums_against(run_dir, dict(trusted_checksums))
    except (ValueError, FileNotFoundError) as exc:
        raise BehaviourProfileError(f"trusted checksum verify failed: {exc}") from exc

    metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
    labels = (
        json.loads(labels_path.read_text(encoding="utf-8"))
        if labels_path.is_file()
        else None
    )
    trades = (
        json.loads(trades_path.read_text(encoding="utf-8"))
        if trades_path.is_file()
        else None
    )
    if not isinstance(metrics, dict):
        raise BehaviourProfileError("regime_metrics.json must be an object")
    return evaluate_behaviour_profile(
        regime_metrics=metrics,
        regime_labels=labels if isinstance(labels, dict) else None,
        trades=trades if isinstance(trades, list) else None,
        policy_version=policy_version,
    )


# Re-export for tests
__all__ = [
    "BEHAVIOUR_PROFILE_FILENAME",
    "BEHAVIOUR_PROFILE_SCHEMA_VERSION",
    "BehaviourPolicyError",
    "BehaviourProfileError",
    "BehaviourProfileResult",
    "compute_behaviour_id",
    "compute_transition_evidence_hash",
    "evaluate_behaviour_profile",
    "evaluate_behaviour_profile_from_run_dir",
]
