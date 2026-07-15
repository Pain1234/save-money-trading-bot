"""Issue #97 — redundant status/readiness DB read consolidation."""

from __future__ import annotations

pytest_plugins = ["tests.paper_trading.test_readonly_api"]

from datetime import UTC, datetime
from unittest.mock import patch
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from paper_trading.enums import RuntimeStatus
from paper_trading.models import RuntimeState


def test_status_uses_single_runtime_snapshot(readonly_client: TestClient) -> None:
    repo = readonly_client._repo  # type: ignore[attr-defined]
    repo.get_runtime_state.reset_mock()
    readonly_client.get("/api/v1/status")
    assert repo.get_runtime_state.call_count == 1


def test_runtime_last_error_is_sanitized_in_status(readonly_client: TestClient) -> None:
    repo = readonly_client._repo  # type: ignore[attr-defined]
    now = datetime.now(UTC)
    runtime = RuntimeState(
        instance_id=uuid4(),
        status=RuntimeStatus.READY,
        heartbeat_at=now,
        last_error="invalid api_key secret",
        version=1,
    )
    repo.get_runtime_state.return_value = runtime
    body = readonly_client.get("/api/v1/status").json()
    assert body["runtime"]["last_error"] == "sanitized error"


def test_market_data_skips_full_readiness_evaluate(readonly_client: TestClient) -> None:
    with patch("paper_trading.readonly_api.ReadinessService") as readiness_cls:
        readonly_client.get("/api/v1/market-data")
        readiness_cls.assert_not_called()
