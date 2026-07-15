"""FastAPI dependencies for paper trading API."""

from __future__ import annotations

import os
import secrets
import time
from collections.abc import Generator
from dataclasses import dataclass, field
from typing import Annotated

from fastapi import Depends, Header, HTTPException, Request
from sqlalchemy.orm import Session

from paper_trading.config import PaperTradingConfig
from paper_trading.db.session import create_db_engine, create_session_factory
from paper_trading.perf_observability import (
    attach_engine_query_metrics,
    detach_engine_query_metrics,
    get_request_metrics,
)
from paper_trading.repository import PaperTradingRepository


@dataclass
class RateLimiter:
    limit_per_minute: int
    _events: dict[str, list[float]] = field(default_factory=dict)

    def check(self, key: str) -> None:
        now = time.monotonic()
        window_start = now - 60.0
        events = [t for t in self._events.get(key, []) if t >= window_start]
        if len(events) >= self.limit_per_minute:
            raise HTTPException(status_code=429, detail="rate limit exceeded")
        events.append(now)
        self._events[key] = events


def get_config() -> PaperTradingConfig:
    return PaperTradingConfig.from_env()


def get_db_session(
    request: Request,
    config: Annotated[PaperTradingConfig, Depends(get_config)],
) -> Generator[Session, None, None]:
    engine = create_db_engine(
        str(config.database_url),
        application_name="paper-readonly-api",
    )
    factory = create_session_factory(engine)
    session = factory()
    metrics = get_request_metrics(request)
    before, after = attach_engine_query_metrics(engine, metrics)
    try:
        yield session
    finally:
        detach_engine_query_metrics(engine, before, after)
        session.close()
        engine.dispose()


def get_repository(
    session: Annotated[Session, Depends(get_db_session)],
) -> PaperTradingRepository:
    return PaperTradingRepository(session)


def get_rate_limiter(
    config: Annotated[PaperTradingConfig, Depends(get_config)],
) -> RateLimiter:
    return RateLimiter(limit_per_minute=config.control_api_rate_limit_per_minute)


def require_control_api(
    request: Request,
    config: Annotated[PaperTradingConfig, Depends(get_config)],
) -> None:
    if not config.control_api_enabled:
        raise HTTPException(status_code=404, detail="not found")
    if config.control_api_localhost_only:
        client = request.client
        if client is None or client.host not in {"127.0.0.1", "::1", "localhost"}:
            raise HTTPException(status_code=403, detail="localhost only")


def verify_control_api_key(
    request: Request,
    config: Annotated[PaperTradingConfig, Depends(get_config)],
    rate_limiter: Annotated[RateLimiter, Depends(get_rate_limiter)],
    x_api_key: Annotated[str | None, Header(alias="X-API-Key")] = None,
) -> None:
    require_control_api(request, config)
    expected = os.environ.get("PAPER_CONTROL_API_KEY")
    if not expected:
        raise HTTPException(status_code=503, detail="control api key not configured")
    client_key = x_api_key or ""
    if not secrets.compare_digest(client_key, expected):
        raise HTTPException(status_code=403, detail="invalid api key")
    client_host = request.client.host if request.client else "unknown"
    rate_limiter.check(client_host)


def parse_page_limit(limit: int) -> int:
    if limit < 1:
        raise HTTPException(status_code=400, detail="limit must be >= 1")
    from paper_trading.api_models import MAX_PAGE_LIMIT

    if limit > MAX_PAGE_LIMIT:
        raise HTTPException(status_code=400, detail=f"limit must be <= {MAX_PAGE_LIMIT}")
    return limit
