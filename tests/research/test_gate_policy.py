"""Unit tests for versioned gate policy + content hashing (Issue #248 / P4.7c)."""

from __future__ import annotations

from decimal import Decimal

import pytest
from research import gate_policy as gp


def test_known_policy_version_returns_policy() -> None:
    policy = gp.get_policy("1.0")
    assert policy.version == "1.0"
    assert len(policy.gates) > 0
    assert all(isinstance(g.name, str) and g.name for g in policy.gates)


def test_unknown_policy_version_raises() -> None:
    with pytest.raises(gp.GatePolicyError):
        gp.get_policy("999.0")


def test_content_hash_is_deterministic() -> None:
    policy = gp.get_policy("1.0")
    a = gp.compute_policy_content_hash(policy)
    b = gp.compute_policy_content_hash(policy)
    assert a == b
    assert a == gp.POLICY_1_0_CONTENT_HASH
    assert len(a) == 64
    int(a, 16)  # must be valid hex


def test_content_hash_changes_when_a_threshold_changes() -> None:
    policy = gp.get_policy("1.0")
    last = policy.gates[-1]
    mutated = gp.GatePolicy(
        version=policy.version,
        description=policy.description,
        gates=(
            *policy.gates[:-1],
            gp.GateDefinition(
                name=last.name,
                metric=last.metric,
                comparator=last.comparator,
                threshold="12345",
                description=last.description,
            ),
        ),
    )
    assert gp.compute_policy_content_hash(policy) != gp.compute_policy_content_hash(mutated)


def test_content_hash_stable_across_gate_reordering_is_not_assumed() -> None:
    """Gate order is part of the canonical content (tuple, not a set) —
    reordering IS a content change, since it can change evaluation reporting
    order for humans reviewing accept/reject reasons."""
    policy = gp.get_policy("1.0")
    if len(policy.gates) < 2:
        pytest.skip("policy needs >= 2 gates for this test")
    reordered = gp.GatePolicy(
        version=policy.version,
        description=policy.description,
        gates=(policy.gates[1], policy.gates[0], *policy.gates[2:]),
    )
    assert gp.compute_policy_content_hash(policy) != gp.compute_policy_content_hash(reordered)


def test_verify_policy_content_hash_passes_for_unchanged_policy() -> None:
    policy = gp.get_policy("1.0")
    expected = gp.compute_policy_content_hash(policy)
    gp.verify_policy_content_hash("1.0", expected)  # must not raise


def test_verify_policy_content_hash_rejects_stale_hash() -> None:
    with pytest.raises(gp.GatePolicyError, match="content hash mismatch"):
        gp.verify_policy_content_hash("1.0", "0" * 64)


def test_verify_policy_content_hash_detects_silent_edit_under_same_version(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Mandatory #248 requirement: reject changed policy content under the
    SAME version number. A persisted record's hash was computed from the
    original '1.0' definition; if '1.0' is later silently edited in the
    registry (same version string, different gates), re-verification of the
    OLD persisted hash against the CURRENT '1.0' definition must fail.
    """
    original_policy = gp.get_policy("1.0")
    persisted_hash = gp.compute_policy_content_hash(original_policy)

    edited_policy = gp.GatePolicy(
        version="1.0",
        description=original_policy.description,
        gates=(
            gp.GateDefinition(
                name="min_closed_trades",
                metric="closed_trades",
                comparator="gte",
                threshold="99999",  # silently changed threshold, same version
            ),
        ),
    )
    monkeypatch.setitem(gp._POLICY_REGISTRY, "1.0", edited_policy)

    with pytest.raises(gp.GatePolicyError, match="content hash mismatch"):
        gp.verify_policy_content_hash("1.0", persisted_hash)


def test_evaluate_comparator_gte() -> None:
    assert gp.evaluate_comparator("gte", Decimal("5"), Decimal("5")) is True
    assert gp.evaluate_comparator("gte", Decimal("4"), Decimal("5")) is False


def test_evaluate_comparator_gt() -> None:
    assert gp.evaluate_comparator("gt", Decimal("6"), Decimal("5")) is True
    assert gp.evaluate_comparator("gt", Decimal("5"), Decimal("5")) is False


def test_evaluate_comparator_lte_lt_eq() -> None:
    assert gp.evaluate_comparator("lte", Decimal("5"), Decimal("5")) is True
    assert gp.evaluate_comparator("lt", Decimal("5"), Decimal("5")) is False
    assert gp.evaluate_comparator("eq", Decimal("5"), Decimal("5")) is True


def test_evaluate_comparator_unknown_raises() -> None:
    with pytest.raises(gp.GatePolicyError):
        gp.evaluate_comparator("nope", Decimal("1"), Decimal("1"))  # type: ignore[arg-type]


def test_list_policy_versions_contains_1_0() -> None:
    assert "1.0" in gp.list_policy_versions()


def test_list_policy_versions_contains_1_1() -> None:
    assert "1.1" in gp.list_policy_versions()


def test_gate_definition_to_dict_round_trip_shape() -> None:
    policy = gp.get_policy("1.0")
    gate = policy.gates[0]
    d = gate.to_dict()
    # Empty category omitted so policy 1.0 content hash stays frozen (#286).
    assert set(d) == {"name", "metric", "comparator", "threshold", "description"}
    categorized = gp.get_policy("1.1").gates[0].to_dict()
    assert "category" in categorized


def test_policy_to_dict_shape() -> None:
    policy = gp.get_policy("1.0")
    d = policy.to_dict()
    assert d["version"] == "1.0"
    assert isinstance(d["gates"], list)
    assert len(d["gates"]) == len(policy.gates)
