"""Tests for read-only API DB instrumentation (P2.5 / Issue #96)."""

from __future__ import annotations

import pytest
from sqlalchemy import text

from paper_trading.db.session import create_db_engine
from paper_trading.perf_observability import (
    RequestPerfMetrics,
    attach_engine_query_metrics,
    detach_engine_query_metrics,
)
from tests.postgres_fixtures import DEFAULT_PG_URL, requires_postgres

pytestmark = [requires_postgres, pytest.mark.postgres]


def test_engine_listeners_record_query_count_and_db_ms() -> None:
    metrics = RequestPerfMetrics(correlation_id="unit-test")
    engine = create_db_engine(DEFAULT_PG_URL, application_name="perf-unit-test")
    before, after = attach_engine_query_metrics(engine, metrics)
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
            conn.commit()
        assert metrics.query_count == 1
        assert metrics.db_ms >= 0.0
    finally:
        detach_engine_query_metrics(engine, before, after)
        engine.dispose()

    stale = RequestPerfMetrics(correlation_id="after-detach")
    before2, after2 = attach_engine_query_metrics(engine, stale)
    detach_engine_query_metrics(engine, before2, after2)
    assert stale.query_count == 0


@requires_postgres
def test_db_session_dependency_records_query_metrics(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from starlette.requests import Request

    from paper_trading.api_dependencies import get_config, get_db_session
    from paper_trading.perf_observability import get_request_metrics
    from tests.postgres_fixtures import _postgres_url

    monkeypatch.setenv("PAPER_TRADING_DATABASE_URL", _postgres_url())
    scope: dict[str, object] = {"type": "http", "method": "GET", "path": "/api/v1/wallet", "headers": []}
    request = Request(scope)
    metrics = get_request_metrics(request)
    generator = get_db_session(request, get_config())
    session = next(generator)
    session.execute(text("SELECT 1 FROM paper_wallet LIMIT 1"))
    generator.close()
    assert metrics.query_count >= 1
    assert metrics.db_ms >= 0.0
