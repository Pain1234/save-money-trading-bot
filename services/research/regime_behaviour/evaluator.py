"""Build ``behavior_profile.json`` from regime metrics + labels (#289)."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from research.artifacts import load_checksums, verify_checksums_against
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


def compute_behaviour_id(
    *,
    run_id: str,
    quality_id: str,
    policy_version: str,
    policy_content_hash: str,
) -> str:
    digest = hashlib.sha256(
        _canonical_json_bytes(
            {
                "policy_content_hash": policy_content_hash,
                "policy_version": policy_version,
                "quality_id": quality_id,
                "run_id": run_id,
            }
        )
    ).hexdigest()
    return f"bh_{digest}"


@dataclass(frozen=True)
class BehaviourProfileResult:
    artifact: dict[str, Any]
    behaviour_id: str


def evaluate_behaviour_profile(
    *,
    regime_metrics: Mapping[str, Any],
    regime_labels: Mapping[str, Any] | None = None,
    trades: Sequence[Mapping[str, Any]] | None = None,
    policy_version: str = "1.0",
) -> BehaviourProfileResult:
    """Derive deterministic behaviour + transition-risk labels.

    No LLM. Persisted labels come only from versioned rules over raw metrics.
    """
    if regime_metrics.get("decision_binding") is True:
        raise BehaviourProfileError(
            "refusing decision_binding=true regime_metrics as behaviour input"
        )

    policy = get_behaviour_policy(policy_version)
    policy_hash = compute_policy_content_hash(policy)
    run_id = str(regime_metrics.get("run_id") or "")
    quality_id = str(regime_metrics.get("quality_id") or "")
    if not run_id or not quality_id:
        raise BehaviourProfileError("regime_metrics missing run_id / quality_id")

    # Pin consistency with labels when provided.
    if regime_labels is not None:
        for key in ("dataset_id", "dataset_content_hash", "run_id"):
            # run_id may only be on metrics; labels use classification pins.
            if key == "run_id":
                continue
            left = str(regime_metrics.get(key) or "")
            right = str(regime_labels.get(key) or "")
            if left and right and left != right:
                raise BehaviourProfileError(
                    f"pin mismatch on {key}: metrics={left!r} labels={right!r}"
                )

    regimes_out: list[dict[str, Any]] = []
    all_weaknesses: list[str] = []
    all_strengths: list[str] = []
    for row in regime_metrics.get("regimes") or []:
        if not isinstance(row, dict):
            continue
        labels = derive_regime_labels(row, policy)
        weakness = pick_main_weakness(labels)
        strength = pick_main_strength(labels)
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

    transitions = []
    day_events = []
    if regime_labels is not None:
        transitions = list(regime_labels.get("transitions") or [])
        day_events = list(regime_labels.get("day_events") or [])
    transition_risk = build_transition_risk_profile(
        transitions=transitions,
        day_events=day_events,
        trades=list(trades) if trades else None,
    )

    evidence = str(regime_metrics.get("evidence_status") or "OK")
    behaviour_id = compute_behaviour_id(
        run_id=run_id,
        quality_id=quality_id,
        policy_version=policy.version,
        policy_content_hash=policy_hash,
    )

    # Global main weakness/strength: first by priority across regimes.
    global_weakness = None
    for candidate in (
        "TAIL_RISK_EXPOSED",
        "WHIPSAW_PRONE",
        "SHOCK_DEPENDENT",
        "COST_INTENSIVE",
        "OVERACTIVE_REENTRY",
        "LATE_EXIT",
        "LATE_ENTRY",
        "CONTROLLED_BLEED",
        "INSUFFICIENT_EVIDENCE",
    ):
        if candidate in all_weaknesses:
            global_weakness = candidate
            break
    global_strength = None
    for candidate in ("PROFITABLE", "DEFENSIVE_INACTIVE"):
        if candidate in all_strengths:
            global_strength = candidate
            break

    artifact: dict[str, Any] = {
        "schema_version": BEHAVIOUR_PROFILE_SCHEMA_VERSION,
        "behaviour_id": behaviour_id,
        "experiment_id": regime_metrics.get("experiment_id"),
        "run_id": run_id,
        "quality_id": quality_id,
        "dataset_id": regime_metrics.get("dataset_id"),
        "dataset_content_hash": regime_metrics.get("dataset_content_hash"),
        "policy_version": policy.version,
        "policy_content_hash": policy_hash,
        "llm_source": False,
        "decision_binding": False,
        "auto_promotion": False,
        "evidence_status": evidence,
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
    trusted_checksums: Mapping[str, str] | None = None,
) -> BehaviourProfileResult:
    """Load sealed run artifacts (checksum-verified) and evaluate behaviour."""
    metrics_path = run_dir / "regime_metrics.json"
    labels_path = run_dir / "regime_labels.json"
    trades_path = run_dir / "trades.json"
    if not metrics_path.is_file():
        raise BehaviourProfileError("missing regime_metrics.json")

    if trusted_checksums is not None:
        try:
            verify_checksums_against(run_dir, dict(trusted_checksums))
        except (ValueError, FileNotFoundError) as exc:
            raise BehaviourProfileError(f"checksum verify failed: {exc}") from exc
    else:
        if not (run_dir / "checksums.json").is_file():
            raise BehaviourProfileError("checksums.json missing")
        try:
            verify_checksums_against(run_dir, load_checksums(run_dir))
        except (ValueError, FileNotFoundError) as exc:
            raise BehaviourProfileError(f"checksum verify failed: {exc}") from exc

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
    "evaluate_behaviour_profile",
    "evaluate_behaviour_profile_from_run_dir",
]
