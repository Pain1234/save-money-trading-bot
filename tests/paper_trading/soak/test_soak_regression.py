"""Regression tests for deterministic paper trading soak."""

from __future__ import annotations

import pytest
from paper_trading.enums import PaperPositionStatus, RuntimeStatus
from paper_trading.runtime import RuntimeService

from tests.paper_trading.conftest import requires_postgres
from tests.paper_trading.e2e.helpers import PaperE2EHarness
from tests.paper_trading.soak.helpers import (
    run_deterministic_soak,
    verify_accounting_independent,
)
from tests.paper_trading.soak.scenarios import reference_coverage_minimums

pytestmark = [requires_postgres, pytest.mark.postgres, pytest.mark.soak]


def test_reference_seed_meets_minimum_coverage(e2e_harness: PaperE2EHarness) -> None:
    report = run_deterministic_soak(e2e_harness, days=365, seed=1)
    report.assert_minimum_coverage(seed=1)
    assert report.entry_fills >= reference_coverage_minimums()["entry_fills"]
    assert report.positions_closed >= reference_coverage_minimums()["positions_closed"]


def test_same_seed_generates_identical_candles() -> None:
    from tests.paper_trading.soak.scenarios import generate_soak_bundle

    one = generate_soak_bundle(days=365, seed=1)
    two = generate_soak_bundle(days=365, seed=1)
    assert one.daily == two.daily
    assert one.weekly == two.weekly
    assert one.monthly == two.monthly


def test_different_seed_changes_candles() -> None:
    from tests.paper_trading.soak.scenarios import generate_soak_bundle

    one = generate_soak_bundle(days=365, seed=1)
    two = generate_soak_bundle(days=365, seed=2)
    assert one.daily != two.daily


def test_different_seed_soak_produces_entries(e2e_harness: PaperE2EHarness) -> None:
    report = run_deterministic_soak(e2e_harness, days=120, seed=2)
    assert report.entry_fills >= 1


def test_independent_wallet_reconstruction(e2e_harness: PaperE2EHarness) -> None:
    run_deterministic_soak(e2e_harness, days=120, seed=1)
    assert verify_accounting_independent(e2e_harness.repo) == []


def test_closed_positions_retain_quantity_without_open_exposure(
    e2e_harness: PaperE2EHarness,
) -> None:
    run_deterministic_soak(e2e_harness, days=120, seed=1)
    for pos in e2e_harness.repo.list_positions(limit=100):
        if pos.status == PaperPositionStatus.CLOSED:
            assert pos.quantity > 0
            assert pos.margin_reserved == 0
    assert len(e2e_harness.repo.get_open_positions()) <= 3


def test_kill_switch_persistent(e2e_harness: PaperE2EHarness) -> None:
    RuntimeService(e2e_harness.repo).set_kill_switch(True)
    runtime = e2e_harness.repo.get_runtime_state()
    assert runtime is not None
    e2e_harness.repo.update_runtime_state(
        status=RuntimeStatus.READY,
        expected_version=runtime.version,
    )
    runtime = e2e_harness.repo.get_runtime_state()
    assert runtime is not None
    assert runtime.kill_switch is True


def test_minimum_coverage_fails_when_thresholds_impossible() -> None:
    from tests.paper_trading.soak.helpers import SoakReport

    report = SoakReport(seed=1, days=365, evaluations=0, entry_fills=0)
    with pytest.raises(AssertionError, match="evaluations"):
        report.assert_minimum_coverage(seed=1)


def test_minimum_coverage_fails_when_fill_path_missing() -> None:
    from tests.paper_trading.soak.helpers import SoakReport

    report = SoakReport(
        seed=1,
        days=365,
        evaluations=300,
        intents_created=6,
        entry_fills=0,
        positions_closed=0,
    )
    with pytest.raises(AssertionError, match="entry_fills"):
        report.assert_minimum_coverage(seed=1)


def test_minimum_coverage_fails_when_stop_path_missing() -> None:
    from tests.paper_trading.soak.helpers import SoakReport

    report = SoakReport(
        seed=1,
        days=365,
        evaluations=300,
        intents_created=6,
        entry_fills=4,
        positions_closed=3,
        trailing_stop_updates=0,
        gap_stops=0,
        intraday_stops=0,
    )
    with pytest.raises(AssertionError, match="trailing_stop_updates"):
        report.assert_minimum_coverage(seed=1)


def test_soak_pause_allows_stop_processing(e2e_harness: PaperE2EHarness) -> None:
    report = run_deterministic_soak(e2e_harness, days=120, seed=1)
    assert report.pause_periods >= 1
    assert report.exit_fills >= 1


def test_soak_double_recovery(e2e_harness: PaperE2EHarness) -> None:
    report = run_deterministic_soak(e2e_harness, days=365, seed=1)
    assert report.recoveries >= 2
