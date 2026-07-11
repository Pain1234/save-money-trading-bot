"""Accelerated deterministic 365-day soak test."""



from __future__ import annotations

import pytest

from tests.paper_trading.conftest import requires_postgres
from tests.paper_trading.e2e.helpers import PaperE2EHarness
from tests.paper_trading.soak.helpers import (
    assert_soak_invariants,
    run_deterministic_soak,
    verify_accounting_independent,
)
from tests.paper_trading.soak.scenarios import reference_coverage_minimums

pytestmark = [requires_postgres, pytest.mark.postgres, pytest.mark.soak]





@pytest.mark.soak

def test_accelerated_365_day_soak(e2e_harness: PaperE2EHarness) -> None:

    report = run_deterministic_soak(e2e_harness, days=365, seed=1)

    assert_soak_invariants(e2e_harness.repo)

    assert verify_accounting_independent(e2e_harness.repo) == []

    report.assert_minimum_coverage(seed=1)

    assert report.ok, report.errors

    assert report.entry_fills >= reference_coverage_minimums()["entry_fills"]

    assert report.runtime_seconds < 180.0

