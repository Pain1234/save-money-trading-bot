"""Versioned gate evaluation policy (Issue #248 / P4.7c / #286).

Policy content is *versioned data*, not code branching on private numbers.
Every :class:`GatePolicy` is registered under a fixed ``version`` string, but
the binding identity for evidence records is the policy's **content hash**
(SHA-256 over its full canonical content), not the version string alone.
This lets a persisted :class:`~research.gate_evaluator.GateRunRecord` detect
if a "frozen" policy version was silently edited later
(:func:`verify_policy_content_hash`).

This module intentionally ships only a small, generic example policy (sample
sufficiency + non-negative PnL / drawdown-floor / robustness-ratio checks
over evidence already produced by the existing research runner (#141-#147)
and robustness orchestrator (#247)). It is infrastructure for a future
Validation Study (#249) and the Regime Evidence Scorecard (#286) — it does
**not** encode the private, human-owned P5 decision rules (see
``docs/research/p5/P5_DECISION_RULES.md``, still "GATES PROPOSED"; final
decision remains #205) and must never be treated as an automatic substitute
for that human sign-off. No live/paper promotion is performed anywhere in
this module or its callers.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal
from typing import Literal

Comparator = Literal["gte", "gt", "lte", "lt", "eq"]

# Scorecard Layer-1 categories (#286 / REGIME_SCORECARD §3). Empty category on
# a GateDefinition means uncategorized (legacy policy 1.0).
GATE_CATEGORIES: frozenset[str] = frozenset(
    {
        "sample_sufficiency",
        "oos_net",
        "drawdown",
        "walk_forward",
        "cost_stress",
        "parameter_fragility",
        "bootstrap",
        "concentration",
        "regime_coverage",
        "execution_realism",
        "behaviour",
        "other",
    }
)

# FAIL / NOT_AVAILABLE in these categories fails the overall gate run (#286).
# ``behaviour`` stays non-critical until #289 lands.
CRITICAL_GATE_CATEGORIES: frozenset[str] = frozenset(
    {
        "sample_sufficiency",
        "oos_net",
        "drawdown",
        "walk_forward",
        "cost_stress",
        "parameter_fragility",
        "bootstrap",
        "concentration",
        "regime_coverage",
        "execution_realism",
    }
)

_COMPARATORS: dict[Comparator, Callable[[Decimal, Decimal], bool]] = {
    "gte": lambda measured, threshold: measured >= threshold,
    "gt": lambda measured, threshold: measured > threshold,
    "lte": lambda measured, threshold: measured <= threshold,
    "lt": lambda measured, threshold: measured < threshold,
    "eq": lambda measured, threshold: measured == threshold,
}


class GatePolicyError(Exception):
    """Unknown policy version, unknown comparator, or content-hash mismatch."""


@dataclass(frozen=True)
class GateDefinition:
    """One named, comparable gate within a policy version.

    ``metric`` is the lookup key into the evaluator's computed measurements
    dict (see ``research.gate_evaluator``); ``threshold`` is stored as a
    canonical Decimal-as-string so the policy content hash is stable.
    ``category`` is optional scorecard Layer-1 labeling (#286); omitted from
    canonical serialization when empty so policy ``1.0`` content hashes stay
    stable.
    """

    name: str
    metric: str
    comparator: Comparator
    threshold: str
    description: str = ""
    category: str = ""

    def __post_init__(self) -> None:
        if self.category and self.category not in GATE_CATEGORIES:
            msg = f"unsupported gate category: {self.category!r}"
            raise GatePolicyError(msg)

    def to_dict(self) -> dict[str, str]:
        payload = {
            "name": self.name,
            "metric": self.metric,
            "comparator": self.comparator,
            "threshold": self.threshold,
            "description": self.description,
        }
        # Omit empty category so policy 1.0 content hash remains unchanged.
        if self.category:
            payload["category"] = self.category
        return payload


@dataclass(frozen=True)
class GatePolicy:
    """One versioned, immutable set of gate definitions."""

    version: str
    description: str
    gates: tuple[GateDefinition, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "version": self.version,
            "description": self.description,
            "gates": [g.to_dict() for g in self.gates],
        }


def _canonical_json_bytes(payload: object) -> bytes:
    return json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def compute_policy_content_hash(policy: GatePolicy) -> str:
    """SHA-256 over the policy's full semantic content (not just its version)."""
    return hashlib.sha256(_canonical_json_bytes(policy.to_dict())).hexdigest()


def is_critical_category(category: str) -> bool:
    """True when FAIL/NOT_AVAILABLE in this category must fail the overall run."""
    return bool(category) and category in CRITICAL_GATE_CATEGORIES


# --- Registered policy versions ---------------------------------------------
# Content is generic example data, not private research results. Extend by
# adding a NEW version key below; never mutate an existing version's `gates`
# tuple in place — that is exactly the silent-edit-under-the-same-version
# failure mode `verify_policy_content_hash` exists to catch
# (see tests/research/test_gate_policy.py).

_GATES_1_0: tuple[GateDefinition, ...] = (
    GateDefinition(
        name="min_closed_trades",
        metric="closed_trades",
        comparator="gte",
        threshold="10",
        description="Sample sufficiency floor (generic example default).",
    ),
    GateDefinition(
        name="net_pnl_non_negative",
        metric="net_pnl",
        comparator="gte",
        threshold="0",
        description="Net PnL under base costs must not be negative.",
    ),
    GateDefinition(
        name="max_drawdown_floor",
        metric="max_drawdown",
        comparator="gte",
        threshold="-0.5",
        description=(
            "Max drawdown must not be worse than -50% of starting "
            "capital (generic example default)."
        ),
    ),
    GateDefinition(
        name="walk_forward_fold_pass_ratio",
        metric="walk_forward_fold_pass_ratio",
        comparator="gte",
        threshold="0.5",
        description=(
            "Share of walk-forward folds (robustness manifest, "
            "#247) with net PnL >= 0 under base costs."
        ),
    ),
    GateDefinition(
        name="cost_stress_combined_elevated_non_negative",
        metric="cost_stress_combined_elevated_net_pnl",
        comparator="gte",
        threshold="0",
        description=(
            "Cost-stress child 'combined_elevated' net PnL "
            "(robustness manifest, #247) must not be negative."
        ),
    ),
    GateDefinition(
        name="parameter_neighbor_pass_ratio",
        metric="parameter_neighbor_pass_ratio",
        comparator="gte",
        threshold="0.5",
        description=(
            "Share of parameter-stability neighbors (robustness "
            "manifest, #247) with net PnL >= 0."
        ),
    ),
    GateDefinition(
        name="bootstrap_q05_net_pnl_non_negative",
        metric="bootstrap_q05_net_pnl",
        comparator="gte",
        threshold="0",
        description=(
            "Bootstrap 5% path net-PnL quantile (robustness "
            "manifest, #247) must not be negative."
        ),
    ),
)

# Category map for policy 1.1 — same thresholds/metrics as 1.0, plus Layer-1 labels.
_CATEGORY_BY_GATE_NAME: dict[str, str] = {
    "min_closed_trades": "sample_sufficiency",
    "net_pnl_non_negative": "oos_net",
    "max_drawdown_floor": "drawdown",
    "walk_forward_fold_pass_ratio": "walk_forward",
    "cost_stress_combined_elevated_non_negative": "cost_stress",
    "parameter_neighbor_pass_ratio": "parameter_fragility",
    "bootstrap_q05_net_pnl_non_negative": "bootstrap",
}

_GATES_1_1: tuple[GateDefinition, ...] = tuple(
    GateDefinition(
        name=g.name,
        metric=g.metric,
        comparator=g.comparator,
        threshold=g.threshold,
        description=g.description,
        category=_CATEGORY_BY_GATE_NAME[g.name],
    )
    for g in _GATES_1_0
)

_POLICY_REGISTRY: dict[str, GatePolicy] = {
    "1.0": GatePolicy(
        version="1.0",
        description=(
            "Generic P4.7c example gate policy: structural sufficiency and "
            "sign checks over evidence already produced by the research "
            "runner and robustness orchestrator. Not the P5 human decision "
            "rules (see docs/research/p5/P5_DECISION_RULES.md, #205)."
        ),
        gates=_GATES_1_0,
    ),
    "1.1": GatePolicy(
        version="1.1",
        description=(
            "Scorecard integrity profile (#286): same generic thresholds as "
            "1.0 plus Layer-1 critical-gate categories. Integrity status is "
            "evaluated separately; missing evidence yields NOT_AVAILABLE, "
            "never PASS. Not the P5 human decision rules (#205)."
        ),
        gates=_GATES_1_1,
    ),
}


def get_policy(version: str) -> GatePolicy:
    try:
        return _POLICY_REGISTRY[version]
    except KeyError as exc:
        msg = f"unknown gate policy version: {version!r}"
        raise GatePolicyError(msg) from exc


def list_policy_versions() -> tuple[str, ...]:
    return tuple(sorted(_POLICY_REGISTRY))


def verify_policy_content_hash(version: str, expected_content_hash: str) -> None:
    """Fail closed if a persisted record's policy hash no longer matches the
    in-repo definition for that version (content changed under the same
    version number).
    """
    policy = get_policy(version)
    actual = compute_policy_content_hash(policy)
    if actual != expected_content_hash:
        msg = (
            f"policy content hash mismatch for version {version!r}: "
            f"persisted={expected_content_hash!r} current={actual!r} "
            "(policy content changed under the same version number)"
        )
        raise GatePolicyError(msg)


def evaluate_comparator(comparator: str, measured: Decimal, threshold: Decimal) -> bool:
    try:
        fn = _COMPARATORS[comparator]  # type: ignore[index]
    except KeyError as exc:
        msg = f"unknown comparator: {comparator!r}"
        raise GatePolicyError(msg) from exc
    return fn(measured, threshold)
