"""Request-scoped performance metrics for the read-only API (P2.5)."""

from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import event
from sqlalchemy.engine import Engine
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

logger = logging.getLogger("paper_trading.readonly_api.perf")

CORRELATION_HEADER = "X-Correlation-Id"
PERF_LOG_ATTR = "perf_metrics"


@dataclass
class RequestPerfMetrics:
    correlation_id: str
    query_count: int = 0
    db_ms: float = 0.0
    started_at: float = field(default_factory=time.perf_counter)

    def record_query(self, duration_ms: float) -> None:
        self.query_count += 1
        self.db_ms += duration_ms


def attach_engine_query_metrics(engine: Engine, metrics: RequestPerfMetrics) -> tuple[Any, Any]:
    """Register cursor timing listeners on the Engine (all connections for this request)."""

    def _before(
        _conn: Any,
        _cursor: Any,
        _statement: str,
        _parameters: Any,
        context: Any,
        _executemany: bool,
    ) -> None:
        if context is not None:
            context._perf_start = time.perf_counter()  # noqa: SLF001

    def _after(
        _conn: Any,
        _cursor: Any,
        _statement: str,
        _parameters: Any,
        context: Any,
        _executemany: bool,
    ) -> None:
        if context is not None and hasattr(context, "_perf_start"):
            elapsed_ms = (time.perf_counter() - context._perf_start) * 1000.0  # noqa: SLF001
            metrics.record_query(elapsed_ms)

    event.listen(engine, "before_cursor_execute", _before)
    event.listen(engine, "after_cursor_execute", _after)
    return _before, _after


def detach_engine_query_metrics(engine: Engine, before: Any, after: Any) -> None:
    event.remove(engine, "before_cursor_execute", before)
    event.remove(engine, "after_cursor_execute", after)


def get_request_metrics(request: Request) -> RequestPerfMetrics:
    metrics = getattr(request.state, PERF_LOG_ATTR, None)
    if metrics is None:
        metrics = RequestPerfMetrics(correlation_id=str(uuid.uuid4()))
        setattr(request.state, PERF_LOG_ATTR, metrics)
    return metrics


class PerformanceLoggingMiddleware(BaseHTTPMiddleware):
    """Log structured per-request timing without sensitive payloads."""

    async def dispatch(self, request: Request, call_next) -> Response:  # type: ignore[no-untyped-def]
        correlation_id = request.headers.get(CORRELATION_HEADER) or str(uuid.uuid4())
        metrics = RequestPerfMetrics(correlation_id=correlation_id)
        setattr(request.state, PERF_LOG_ATTR, metrics)
        started = time.perf_counter()
        response = await call_next(request)
        total_ms = (time.perf_counter() - started) * 1000.0
        response_bytes = 0
        if response.headers.get("content-length"):
            try:
                response_bytes = int(response.headers["content-length"])
            except ValueError:
                response_bytes = 0
        logger.info(
            "route=%s total_ms=%.1f db_ms=%.1f query_count=%d response_bytes=%d "
            "status_code=%d correlation_id=%s",
            request.url.path,
            total_ms,
            metrics.db_ms,
            metrics.query_count,
            response_bytes,
            response.status_code,
            correlation_id,
        )
        response.headers[CORRELATION_HEADER] = correlation_id
        # Skip Cache-Control on health/readiness probes (Issue #99).
        if request.url.path not in {"/health", "/readiness"}:
            max_age = _cache_max_age(request.url.path)
            if max_age is not None:
                response.headers["Cache-Control"] = f"private, max-age={max_age}"
        return response


def _cache_max_age(path: str) -> int | None:
    """P2.5 initial cache TTLs (seconds) for read-only monitoring routes."""
    if path in {"/api/v1/status", "/api/v1/market-data", "/api/v1/dashboard-summary"}:
        return 2
    if path in {"/api/v1/wallet", "/api/v1/positions"}:
        return 5
    if path.startswith("/api/v1/orders") or path.startswith("/api/v1/fills"):
        return 5
    if path.startswith("/api/v1/equity") or path.startswith("/api/v1/events"):
        return 30
    if path.startswith("/api/v1/scheduler-runs"):
        return 30
    return None
