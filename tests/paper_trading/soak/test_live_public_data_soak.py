"""Optional bounded live public Hyperliquid testnet soak."""

from __future__ import annotations

import os

import pytest

pytestmark = pytest.mark.live


def test_live_public_data_soak_skipped_by_default() -> None:
    if os.environ.get("RUN_PAPER_LIVE_SOAK", "0") != "1":
        pytest.skip("RUN_PAPER_LIVE_SOAK not enabled")
    if os.environ.get("HYPERLIQUID_NETWORK", "") != "testnet":
        pytest.skip("HYPERLIQUID_NETWORK must be testnet")
    max_seconds = min(int(os.environ.get("PAPER_LIVE_SOAK_SECONDS", "300")), 600)
    assert max_seconds > 0
    # Bounded live soak validates transport only; no orders or wallet usage.
    pytest.skip("live soak transport check placeholder — no trade required in short window")
