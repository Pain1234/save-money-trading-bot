"""Tests for restore drill snapshot helpers."""

from __future__ import annotations

from scripts.restore_drill_snapshot import assert_business_data_present, compare_snapshots


def test_compare_snapshots_ok() -> None:
    snapshot = {
        "row_counts": {"paper_fills": 2},
        "wallet": {"cash": "99900"},
        "open_positions": 0,
        "closed_positions": 1,
        "fill_count": 2,
    }
    assert compare_snapshots(snapshot, dict(snapshot)) == []


def test_compare_snapshots_detects_wallet_mismatch() -> None:
    base = {
        "row_counts": {"paper_fills": 2},
        "wallet": {"cash": "99900"},
        "open_positions": 0,
        "closed_positions": 1,
        "fill_count": 2,
    }
    other = dict(base)
    other["wallet"] = {"cash": "100000"}
    issues = compare_snapshots(base, other)
    assert any("wallet mismatch" in issue for issue in issues)


def test_assert_business_data_present_requires_fills() -> None:
    snapshot = {
        "row_counts": {"strategy_evaluations": 1, "paper_fills": 0},
        "wallet": {"cash": "99000"},
        "closed_positions": 0,
        "fill_count": 0,
    }
    issues = assert_business_data_present(snapshot)
    assert len(issues) >= 2
