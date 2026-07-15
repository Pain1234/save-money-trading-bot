"""Tests for opt-in Layer-C residual breakdown headers (Issue #121)."""

from __future__ import annotations

import time
from collections.abc import Generator
from datetime import UTC, datetime
from decimal import Decimal
from typing import Annotated, Any
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from fastapi import Depends
from fastapi.testclient import TestClient
from paper_trading import api_dependencies
from paper_trading.config import PaperTradingConfig
from paper_trading.enums import RuntimeStatus
from paper_trading.models import PaperWalletState, RuntimeState
from paper_trading.readonly_api import app
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool


@pytest.fixture
def sqlite_engine() -> Generator[Engine, None, None]:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    yield engine
    engine.dispose()


def test_breakdown_headers_absent_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PAPER_API_PERF_BREAKDOWN", raising=False)
    app.dependency_overrides.clear()
    client = TestClient(app)
    response = client.get("/health")
    assert response.status_code == 200
    assert "X-Perf-Engine-Create-Ms" not in response.headers


def test_breakdown_headers_present_on_db_wallet_route(
    monkeypatch: pytest.MonkeyPatch, sqlite_engine: Engine
) -> None:
    """DB-backed /wallet must run get_db_session so setup timings are non-zero."""
    monkeypatch.setenv("PAPER_API_PERF_BREAKDOWN", "1")

    config = PaperTradingConfig(
        database_url="postgresql://postgres:postgres@localhost:5432/paper_trading_test"
    )

    def _create_engine(_url: str, **_kwargs: Any) -> Engine:
        # Guarantee measurable engine_create_ms (header uses one decimal place).
        time.sleep(0.002)
        return sqlite_engine

    monkeypatch.setattr(api_dependencies, "create_db_engine", _create_engine)
    monkeypatch.setattr(
        api_dependencies,
        "create_session_factory",
        lambda engine: sessionmaker(
            bind=engine, autoflush=False, autocommit=False, expire_on_commit=False
        ),
    )

    def override_get_repository(
        session: Annotated[Session, Depends(api_dependencies.get_db_session)],
    ) -> MagicMock:
        session.execute(text("SELECT 1"))
        now = datetime.now(UTC)
        repo = MagicMock()
        repo.get_wallet.return_value = PaperWalletState(
            wallet_id=uuid4(),
            cash=Decimal("1"),
            total_realized_pnl=Decimal("0"),
            total_fees=Decimal("0"),
            total_funding=Decimal("0"),
            total_slippage=Decimal("0"),
            version=1,
            updated_at=now,
        )
        repo.get_runtime_state.return_value = RuntimeState(
            instance_id=uuid4(),
            status=RuntimeStatus.READY,
            heartbeat_at=now,
            version=1,
        )
        repo.get_open_positions.return_value = ()
        return repo

    app.dependency_overrides.clear()
    app.dependency_overrides[api_dependencies.get_config] = lambda: config
    app.dependency_overrides[api_dependencies.get_repository] = override_get_repository
    try:
        client = TestClient(app, raise_server_exceptions=False)
        response = client.get("/api/v1/wallet")
        assert response.status_code == 200
        assert "X-Perf-Engine-Create-Ms" in response.headers
        assert "X-Perf-Session-Setup-Ms" in response.headers
        assert "X-Perf-Pool-Connect-Ms" in response.headers
        assert float(response.headers["X-Perf-Engine-Create-Ms"]) > 0.0
        assert float(response.headers["X-Perf-Session-Setup-Ms"]) >= 0.0
        assert float(response.headers["X-Perf-Pool-Connect-Ms"]) > 0.0
    finally:
        app.dependency_overrides.clear()
