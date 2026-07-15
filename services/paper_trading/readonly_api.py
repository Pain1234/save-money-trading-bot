"""Read-only FastAPI monitoring service for Railway deployment."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Annotated, Any
from uuid import UUID

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from paper_trading.api import (
    _position_response,
    _sanitize_error,
    _sanitize_payload,
)
from paper_trading.api_dependencies import get_config, get_repository, parse_page_limit
from paper_trading.api_models import (
    AuditEventResponse,
    FillResponse,
    HealthResponse,
    OrderResponse,
    PaginatedResponse,
    PortfolioResponse,
    ReadinessResponse,
    RuntimeResponse,
    SchedulerRunResponse,
    WalletResponse,
    decode_cursor,
    encode_cursor,
    format_decimal,
    format_utc,
    format_uuid,
)
from paper_trading.clock import SystemClock
from paper_trading.config import PaperTradingConfig
from paper_trading.enums import RuntimeStatus
from paper_trading.models import RuntimeState
from paper_trading.readiness import ReadinessService
from paper_trading.repository import PaperTradingRepository
from paper_trading.perf_observability import PerformanceLoggingMiddleware

app = FastAPI(title="Paper Trading Read-only API", version="1.0.0", openapi_url=None)


class ReadonlyMethodMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):  # type: ignore[no-untyped-def]
        if request.method not in {"GET", "HEAD", "OPTIONS"}:
            return JSONResponse(status_code=405, content={"detail": "method not allowed"})
        return await call_next(request)


app.add_middleware(ReadonlyMethodMiddleware)
app.add_middleware(PerformanceLoggingMiddleware)


def _infer_market_data_ready(
    runtime: RuntimeState | None,
    config: PaperTradingConfig,
) -> bool:
    if runtime is None or runtime.status != RuntimeStatus.READY:
        return False
    age = SystemClock().now() - runtime.heartbeat_at
    return age <= timedelta(seconds=config.stale_runtime_threshold_seconds)


def _runtime_readiness_snapshot(
    repo: PaperTradingRepository,
    config: PaperTradingConfig,
) -> tuple[RuntimeState | None, ReadinessResponse]:
    """Single consistent snapshot for status, readiness, and summary endpoints."""
    repo.session.expire_all()
    runtime = repo.get_runtime_state()
    market_data_ready = _infer_market_data_ready(runtime, config)
    snapshot = ReadinessService(repo, config).evaluate(
        market_data_ready=market_data_ready,
        advisory_lock=None,
        scheduler_active=True,
        recovery_active=False,
        runtime=runtime,
    )
    readiness = ReadinessResponse(
        process_liveness=snapshot.process_liveness,
        runtime_readiness=snapshot.runtime_readiness,
        entry_readiness=snapshot.entry_readiness,
        market_data_ready=market_data_ready,
        database_ready="database_unreachable" not in snapshot.reasons,
        migration_at_head="migration_not_at_head" not in snapshot.reasons,
        advisory_lock_held=False,
        paused=runtime.paused if runtime else False,
        kill_switch=runtime.kill_switch if runtime else False,
        reasons=snapshot.reasons,
        last_error=_sanitize_error(runtime.last_error if runtime else None),
    )
    return runtime, readiness


def _runtime_dict(runtime: RuntimeState) -> dict[str, Any]:
    return RuntimeResponse(
        instance_id=format_uuid(runtime.instance_id),
        status=runtime.status.value,
        last_error=_sanitize_error(runtime.last_error),
        started_at=format_utc(runtime.started_at) if runtime.started_at else None,
        heartbeat_at=format_utc(runtime.heartbeat_at),
        kill_switch=runtime.kill_switch,
        paused=runtime.paused,
        current_cycle_id=(
            format_uuid(runtime.current_cycle_id) if runtime.current_cycle_id else None
        ),
        version=runtime.version,
    ).model_dump()


def _display_status(
    runtime: RuntimeState | None,
    readiness: ReadinessResponse,
) -> str:
    if runtime is None:
        return "STOPPED"
    if runtime.status == RuntimeStatus.FAILED:
        return "STOPPED"
    if readiness.runtime_readiness:
        return "READY"
    return "DEGRADED"


def _readiness_body(
    repo: PaperTradingRepository,
    config: PaperTradingConfig,
) -> ReadinessResponse:
    _runtime, readiness = _runtime_readiness_snapshot(repo, config)
    return readiness


def _status_payload(
    repo: PaperTradingRepository,
    config: PaperTradingConfig,
) -> dict[str, Any]:
    runtime, readiness = _runtime_readiness_snapshot(repo, config)
    heartbeat_age_seconds: float | None = None
    if runtime is not None:
        heartbeat_age_seconds = (
            SystemClock().now() - runtime.heartbeat_at
        ).total_seconds()
    display_status = _display_status(runtime, readiness)
    return {
        "display_status": display_status,
        "runtime": _runtime_dict(runtime) if runtime else None,
        "readiness": readiness.model_dump(),
        "heartbeat_age_seconds": heartbeat_age_seconds,
        "stale_heartbeat_threshold_seconds": config.stale_runtime_threshold_seconds,
        "hyperliquid_network": __import__("os").environ.get("HYPERLIQUID_NETWORK", "testnet"),
    }


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse()


@app.get("/readiness", response_model=ReadinessResponse)
def readiness(
    repo: Annotated[PaperTradingRepository, Depends(get_repository)],
    config: Annotated[PaperTradingConfig, Depends(get_config)],
) -> JSONResponse:
    body = _readiness_body(repo, config)
    status_code = 200 if body.runtime_readiness else 503
    response = JSONResponse(content=body.model_dump(), status_code=status_code)
    if status_code != 200:
        response.headers["Cache-Control"] = "no-store"
    return response


@app.get("/api/v1/status")
def api_status(
    repo: Annotated[PaperTradingRepository, Depends(get_repository)],
    config: Annotated[PaperTradingConfig, Depends(get_config)],
) -> dict[str, Any]:
    return _status_payload(repo, config)


@app.get("/api/v1/market-data")
def api_market_data(
    repo: Annotated[PaperTradingRepository, Depends(get_repository)],
    config: Annotated[PaperTradingConfig, Depends(get_config)],
) -> dict[str, Any]:
    repo.session.expire_all()
    runtime = repo.get_runtime_state()
    market_data_ready = _infer_market_data_ready(runtime, config)
    return {
        "hyperliquid_network": __import__("os").environ.get("HYPERLIQUID_NETWORK", "testnet"),
        "market_data_ready": market_data_ready,
        "worker_status": runtime.status.value if runtime else None,
        "worker_heartbeat_at": format_utc(runtime.heartbeat_at) if runtime else None,
        "symbols": list(config.symbols),
    }


@app.get("/api/v1/wallet", response_model=WalletResponse)
def api_wallet(
    repo: Annotated[PaperTradingRepository, Depends(get_repository)],
) -> WalletResponse:
    wallet = repo.get_wallet()
    if wallet is None:
        raise HTTPException(status_code=404, detail="wallet not found")
    return WalletResponse(
        wallet_id=format_uuid(wallet.wallet_id),
        cash=format_decimal(wallet.cash),
        total_realized_pnl=format_decimal(wallet.total_realized_pnl),
        total_fees=format_decimal(wallet.total_fees),
        total_funding=format_decimal(wallet.total_funding),
        total_slippage=format_decimal(wallet.total_slippage),
        version=wallet.version,
        updated_at=format_utc(wallet.updated_at),
    )


@app.get("/api/v1/positions", response_model=PaginatedResponse)
def api_positions(
    repo: Annotated[PaperTradingRepository, Depends(get_repository)],
    limit: Annotated[int, Query(ge=1)] = 50,
    cursor: str | None = None,
) -> PaginatedResponse:
    page_limit = parse_page_limit(limit)
    after_opened_at: datetime | None = None
    after_position_id: UUID | None = None
    if cursor:
        try:
            data = decode_cursor(cursor)
            after_opened_at = datetime.fromisoformat(data["opened_at"].replace("Z", "+00:00"))
            after_position_id = UUID(data["position_id"])
        except (KeyError, ValueError, TypeError) as exc:
            raise HTTPException(status_code=400, detail="invalid cursor") from exc
    rows = repo.list_positions(
        limit=page_limit + 1,
        after_opened_at=after_opened_at,
        after_position_id=after_position_id,
    )
    items = [_position_response(p).model_dump() for p in rows[:page_limit]]
    next_cursor = None
    if len(rows) > page_limit:
        last = rows[page_limit - 1]
        next_cursor = encode_cursor(
            {"opened_at": format_utc(last.opened_at), "position_id": str(last.position_id)}
        )
    return PaginatedResponse(items=items, next_cursor=next_cursor, limit=page_limit)


@app.get("/api/v1/orders", response_model=PaginatedResponse)
def api_orders(
    repo: Annotated[PaperTradingRepository, Depends(get_repository)],
    limit: Annotated[int, Query(ge=1)] = 50,
    cursor: str | None = None,
) -> PaginatedResponse:
    page_limit = parse_page_limit(limit)
    after_created_at: datetime | None = None
    after_order_id: UUID | None = None
    if cursor:
        try:
            data = decode_cursor(cursor)
            after_created_at = datetime.fromisoformat(data["created_at"].replace("Z", "+00:00"))
            after_order_id = UUID(data["paper_order_id"])
        except (KeyError, ValueError, TypeError) as exc:
            raise HTTPException(status_code=400, detail="invalid cursor") from exc
    rows = repo.list_orders(
        limit=page_limit + 1,
        after_created_at=after_created_at,
        after_order_id=after_order_id,
    )
    items = [
        OrderResponse(
            paper_order_id=format_uuid(o.paper_order_id),
            intent_id=format_uuid(o.intent_id),
            symbol=o.symbol,
            side=o.side.value,
            order_type=o.order_type.value,
            requested_quantity=format_decimal(o.requested_quantity),
            remaining_quantity=format_decimal(o.remaining_quantity),
            expected_fill_time=format_utc(o.expected_fill_time),
            status=o.status.value,
            created_at=format_utc(o.created_at),
            updated_at=format_utc(o.updated_at),
        ).model_dump()
        for o in rows[:page_limit]
    ]
    next_cursor = None
    if len(rows) > page_limit:
        last = rows[page_limit - 1]
        next_cursor = encode_cursor(
            {
                "created_at": format_utc(last.created_at),
                "paper_order_id": str(last.paper_order_id),
            }
        )
    return PaginatedResponse(items=items, next_cursor=next_cursor, limit=page_limit)


@app.get("/api/v1/fills", response_model=PaginatedResponse)
def api_fills(
    repo: Annotated[PaperTradingRepository, Depends(get_repository)],
    limit: Annotated[int, Query(ge=1)] = 50,
    cursor: str | None = None,
) -> PaginatedResponse:
    page_limit = parse_page_limit(limit)
    after_fill_time: datetime | None = None
    after_fill_id: UUID | None = None
    if cursor:
        try:
            data = decode_cursor(cursor)
            after_fill_time = datetime.fromisoformat(data["fill_time"].replace("Z", "+00:00"))
            after_fill_id = UUID(data["fill_id"])
        except (KeyError, ValueError, TypeError) as exc:
            raise HTTPException(status_code=400, detail="invalid cursor") from exc
    rows = repo.list_fills(
        limit=page_limit + 1,
        after_fill_time=after_fill_time,
        after_fill_id=after_fill_id,
    )
    items = [
        FillResponse(
            fill_id=format_uuid(f.fill_id),
            paper_order_id=format_uuid(f.paper_order_id) if f.paper_order_id else None,
            position_id=format_uuid(f.position_id) if f.position_id else None,
            fill_kind=f.fill_kind.value,
            symbol=f.symbol,
            side=f.side.value,
            quantity=format_decimal(f.quantity),
            market_open_price=format_decimal(f.market_open_price),
            slippage=format_decimal(f.slippage),
            fill_price=format_decimal(f.fill_price),
            fee=format_decimal(f.fee),
            fill_time=format_utc(f.fill_time),
            candle_key=format_utc(f.candle_key),
            deterministic_fill_key=f.deterministic_fill_key,
            fill_sequence=f.fill_sequence,
        ).model_dump()
        for f in rows[:page_limit]
    ]
    next_cursor = None
    if len(rows) > page_limit:
        last = rows[page_limit - 1]
        next_cursor = encode_cursor(
            {"fill_time": format_utc(last.fill_time), "fill_id": str(last.fill_id)}
        )
    return PaginatedResponse(items=items, next_cursor=next_cursor, limit=page_limit)


@app.get("/api/v1/stops", response_model=PaginatedResponse)
def api_stops(
    repo: Annotated[PaperTradingRepository, Depends(get_repository)],
    limit: Annotated[int, Query(ge=1)] = 50,
    cursor: str | None = None,
) -> PaginatedResponse:
    page_limit = parse_page_limit(limit)
    after_evaluation_time: datetime | None = None
    after_stop_event_id: UUID | None = None
    if cursor:
        try:
            data = decode_cursor(cursor)
            after_evaluation_time = datetime.fromisoformat(
                data["evaluation_time"].replace("Z", "+00:00")
            )
            after_stop_event_id = UUID(data["stop_event_id"])
        except (KeyError, ValueError, TypeError) as exc:
            raise HTTPException(status_code=400, detail="invalid cursor") from exc
    rows = repo.list_stop_events(
        limit=page_limit + 1,
        after_evaluation_time=after_evaluation_time,
        after_stop_event_id=after_stop_event_id,
    )
    items = [
        {
            "stop_event_id": format_uuid(event.stop_event_id),
            "position_id": format_uuid(event.position_id),
            "previous_stop": format_decimal(event.previous_stop),
            "new_stop": format_decimal(event.new_stop),
            "highest_close": format_decimal(event.highest_close),
            "atr": format_decimal(event.atr),
            "evaluation_time": format_utc(event.evaluation_time),
            "reason": event.reason,
        }
        for event in rows[:page_limit]
    ]
    next_cursor = None
    if len(rows) > page_limit:
        last = rows[page_limit - 1]
        next_cursor = encode_cursor(
            {
                "evaluation_time": format_utc(last.evaluation_time),
                "stop_event_id": str(last.stop_event_id),
            }
        )
    return PaginatedResponse(items=items, next_cursor=next_cursor, limit=page_limit)


@app.get("/api/v1/scheduler-runs", response_model=PaginatedResponse)
def api_scheduler_runs(
    repo: Annotated[PaperTradingRepository, Depends(get_repository)],
    limit: Annotated[int, Query(ge=1)] = 50,
    cursor: str | None = None,
) -> PaginatedResponse:
    page_limit = parse_page_limit(limit)
    after_scheduled_for: datetime | None = None
    after_run_id: UUID | None = None
    if cursor:
        try:
            data = decode_cursor(cursor)
            after_scheduled_for = datetime.fromisoformat(
                data["scheduled_for"].replace("Z", "+00:00")
            )
            after_run_id = UUID(data["run_id"])
        except (KeyError, ValueError, TypeError) as exc:
            raise HTTPException(status_code=400, detail="invalid cursor") from exc
    rows = repo.list_scheduler_runs(
        limit=page_limit + 1,
        after_scheduled_for=after_scheduled_for,
        after_run_id=after_run_id,
    )
    items = [
        SchedulerRunResponse(
            run_id=format_uuid(r.run_id),
            job_name=r.job_name,
            scheduled_for=format_utc(r.scheduled_for),
            started_at=format_utc(r.started_at) if r.started_at else None,
            completed_at=format_utc(r.completed_at) if r.completed_at else None,
            status=r.status.value,
            error=_sanitize_error(r.error),
            idempotency_key=r.idempotency_key,
        ).model_dump()
        for r in rows[:page_limit]
    ]
    next_cursor = None
    if len(rows) > page_limit:
        last = rows[page_limit - 1]
        next_cursor = encode_cursor(
            {"scheduled_for": format_utc(last.scheduled_for), "run_id": str(last.run_id)}
        )
    return PaginatedResponse(items=items, next_cursor=next_cursor, limit=page_limit)


@app.get("/api/v1/events", response_model=PaginatedResponse)
def api_events(
    repo: Annotated[PaperTradingRepository, Depends(get_repository)],
    limit: Annotated[int, Query(ge=1)] = 50,
    cursor: str | None = None,
) -> PaginatedResponse:
    page_limit = parse_page_limit(limit)
    after_created_at: datetime | None = None
    after_event_id: UUID | None = None
    if cursor:
        try:
            data = decode_cursor(cursor)
            after_created_at = datetime.fromisoformat(data["created_at"].replace("Z", "+00:00"))
            after_event_id = UUID(data["event_id"])
        except (KeyError, ValueError, TypeError) as exc:
            raise HTTPException(status_code=400, detail="invalid cursor") from exc
    rows = repo.list_audit_events(
        limit=page_limit + 1,
        after_created_at=after_created_at,
        after_event_id=after_event_id,
    )
    items = [
        AuditEventResponse(
            event_id=format_uuid(e.event_id),
            event_type=e.event_type,
            aggregate_type=e.aggregate_type,
            aggregate_id=format_uuid(e.aggregate_id),
            payload_json=_sanitize_payload(e.payload_json),
            cycle_id=format_uuid(e.cycle_id) if e.cycle_id else None,
            created_at=format_utc(e.created_at),
        ).model_dump()
        for e in rows[:page_limit]
    ]
    next_cursor = None
    if len(rows) > page_limit:
        last = rows[page_limit - 1]
        next_cursor = encode_cursor(
            {"created_at": format_utc(last.created_at), "event_id": str(last.event_id)}
        )
    return PaginatedResponse(items=items, next_cursor=next_cursor, limit=page_limit)


@app.get("/api/v1/equity", response_model=PaginatedResponse)
def api_equity(
    repo: Annotated[PaperTradingRepository, Depends(get_repository)],
    limit: Annotated[int, Query(ge=1)] = 50,
    cursor: str | None = None,
) -> PaginatedResponse:
    page_limit = parse_page_limit(limit)
    after_evaluation_time: datetime | None = None
    after_snapshot_id: UUID | None = None
    if cursor:
        try:
            data = decode_cursor(cursor)
            after_evaluation_time = datetime.fromisoformat(
                data["evaluation_time"].replace("Z", "+00:00")
            )
            after_snapshot_id = UUID(data["snapshot_id"])
        except (KeyError, ValueError, TypeError) as exc:
            raise HTTPException(status_code=400, detail="invalid cursor") from exc
    rows = repo.list_portfolio_snapshots(
        limit=page_limit + 1,
        after_evaluation_time=after_evaluation_time,
        after_snapshot_id=after_snapshot_id,
    )
    items = [
        PortfolioResponse(
            snapshot_id=format_uuid(s.snapshot_id),
            evaluation_time=format_utc(s.evaluation_time),
            cash=format_decimal(s.cash),
            margin_used=format_decimal(s.margin_used),
            equity=format_decimal(s.equity),
            unrealized_pnl=format_decimal(s.unrealized_pnl),
            realized_pnl=format_decimal(s.realized_pnl),
            total_open_risk=format_decimal(s.total_open_risk),
            open_position_count=s.open_position_count,
        ).model_dump()
        for s in rows[:page_limit]
    ]
    next_cursor = None
    if len(rows) > page_limit:
        last = rows[page_limit - 1]
        next_cursor = encode_cursor(
            {
                "evaluation_time": format_utc(last.evaluation_time),
                "snapshot_id": str(last.snapshot_id),
            }
        )
    return PaginatedResponse(items=items, next_cursor=next_cursor, limit=page_limit)


@app.exception_handler(Exception)
def generic_exception_handler(_request: Request, _exc: Exception) -> JSONResponse:
    return JSONResponse(status_code=500, content={"detail": "internal error"})


def create_readonly_app() -> FastAPI:
    return app
