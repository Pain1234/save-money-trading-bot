"""FastAPI read and control plane for paper trading."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any
from uuid import UUID, uuid4

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from sqlalchemy.engine import Engine

from paper_trading.api_dependencies import (
    get_config,
    get_repository,
    parse_page_limit,
    verify_control_api_key,
)
from paper_trading.api_models import (
    AuditEventResponse,
    ControlResponse,
    EvaluationResponse,
    FillResponse,
    HealthResponse,
    IntentResponse,
    KillControlRequest,
    OrderResponse,
    PaginatedResponse,
    PortfolioResponse,
    PositionResponse,
    ReadinessResponse,
    RunCycleRequest,
    RuntimeResponse,
    SchedulerRunResponse,
    decode_cursor,
    encode_cursor,
    format_decimal,
    format_utc,
    format_uuid,
)
from paper_trading.app_state import configure_app_state, get_app_state
from paper_trading.config import PaperTradingConfig
from paper_trading.db.orm import SchedulerRunRow
from paper_trading.db.transaction import transaction_scope
from paper_trading.enums import KillSwitchClosePolicy, SchedulerRunStatus
from paper_trading.ids import scheduler_run_key
from paper_trading.lock import PostgresAdvisoryLock
from paper_trading.readiness import ReadinessService
from paper_trading.recovery import RecoveryService
from paper_trading.repository import PaperTradingRepository
from paper_trading.runtime import RuntimeService
from paper_trading.scheduler import SchedulerJobName

app = FastAPI(title="Paper Trading Orchestrator", version="1.0.0")


def _market_data_ready() -> bool:
    return get_app_state().market_data_ready()


def _advisory_lock_for_recover(
    config: PaperTradingConfig,
    repo: PaperTradingRepository,
) -> PostgresAdvisoryLock:
    state_lock = get_app_state().advisory_lock
    if isinstance(state_lock, PostgresAdvisoryLock):
        return state_lock
    bind = repo.session.get_bind()
    engine = bind.engine if hasattr(bind, "engine") else bind
    assert isinstance(engine, Engine)
    return PostgresAdvisoryLock(engine, config.advisory_lock_id)


def _scheduler_active(config: PaperTradingConfig) -> bool:
    state = get_app_state()
    return state.scheduler_active or not config.scheduler_enabled


def set_market_data_ready(value: bool) -> None:
    configure_app_state(market_data_ready=lambda: value)


def set_scheduler_active(value: bool) -> None:
    configure_app_state(scheduler_active=value)


def _runtime_response(repo: PaperTradingRepository) -> RuntimeResponse:
    runtime = repo.get_runtime_state()
    if runtime is None:
        raise HTTPException(status_code=503, detail="runtime state missing")
    return RuntimeResponse(
        instance_id=format_uuid(runtime.instance_id),
        status=runtime.status.value,
        last_error=runtime.last_error,
        started_at=format_utc(runtime.started_at) if runtime.started_at else None,
        heartbeat_at=format_utc(runtime.heartbeat_at),
        kill_switch=runtime.kill_switch,
        paused=runtime.paused,
        current_cycle_id=(
            format_uuid(runtime.current_cycle_id) if runtime.current_cycle_id else None
        ),
        version=runtime.version,
    )


def _position_response(position: Any) -> PositionResponse:
    return PositionResponse(
        position_id=format_uuid(position.position_id),
        symbol=position.symbol,
        status=position.status.value,
        quantity=format_decimal(position.quantity),
        average_entry_price=format_decimal(position.average_entry_price),
        initial_stop=format_decimal(position.initial_stop),
        current_stop=format_decimal(position.current_stop),
        highest_close_since_entry=format_decimal(position.highest_close_since_entry),
        entry_atr14=format_decimal(position.entry_atr14),
        realized_pnl=format_decimal(position.realized_pnl),
        unrealized_pnl=format_decimal(position.unrealized_pnl),
        margin_reserved=format_decimal(position.margin_reserved),
        entry_intent_id=format_uuid(position.entry_intent_id),
        opened_at=format_utc(position.opened_at),
        closed_at=format_utc(position.closed_at) if position.closed_at else None,
        version=position.version,
    )


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse()


@app.get("/readiness", response_model=ReadinessResponse)
def readiness(
    repo: Annotated[PaperTradingRepository, Depends(get_repository)],
    config: Annotated[PaperTradingConfig, Depends(get_config)],
) -> JSONResponse:
    readiness_svc = ReadinessService(repo, config)
    snapshot = readiness_svc.evaluate(
        market_data_ready=_market_data_ready(),
        advisory_lock=get_app_state().advisory_lock,
        scheduler_active=_scheduler_active(config),
        recovery_active=RecoveryService.is_recovery_active(),
    )
    runtime = repo.get_runtime_state()
    body = ReadinessResponse(
        process_liveness=snapshot.process_liveness,
        runtime_readiness=snapshot.runtime_readiness,
        entry_readiness=snapshot.entry_readiness,
        market_data_ready=_market_data_ready(),
        database_ready="database_unreachable" not in snapshot.reasons,
        migration_at_head="migration_not_at_head" not in snapshot.reasons,
        advisory_lock_held=(
            lock.held if (lock := get_app_state().advisory_lock) is not None else False
        ),
        paused=runtime.paused if runtime else False,
        kill_switch=runtime.kill_switch if runtime else False,
        reasons=snapshot.reasons,
        last_error=_sanitize_error(runtime.last_error if runtime else None),
    )
    status_code = 200 if snapshot.runtime_readiness else 503
    return JSONResponse(content=body.model_dump(), status_code=status_code)


@app.get("/runtime", response_model=RuntimeResponse)
def get_runtime(
    repo: Annotated[PaperTradingRepository, Depends(get_repository)],
) -> RuntimeResponse:
    return _runtime_response(repo)


@app.get("/portfolio", response_model=PortfolioResponse)
def get_portfolio(
    repo: Annotated[PaperTradingRepository, Depends(get_repository)],
) -> PortfolioResponse:
    snapshot = repo.get_latest_portfolio_snapshot()
    wallet = repo.get_wallet()
    if snapshot is None and wallet is None:
        raise HTTPException(status_code=404, detail="portfolio not found")
    if snapshot is not None:
        return PortfolioResponse(
            snapshot_id=format_uuid(snapshot.snapshot_id),
            evaluation_time=format_utc(snapshot.evaluation_time),
            cash=format_decimal(snapshot.cash),
            margin_used=format_decimal(snapshot.margin_used),
            equity=format_decimal(snapshot.equity),
            unrealized_pnl=format_decimal(snapshot.unrealized_pnl),
            realized_pnl=format_decimal(snapshot.realized_pnl),
            total_open_risk=format_decimal(snapshot.total_open_risk),
            open_position_count=snapshot.open_position_count,
        )
    assert wallet is not None
    return PortfolioResponse(
        snapshot_id=None,
        evaluation_time=format_utc(wallet.updated_at),
        cash=format_decimal(wallet.cash),
        margin_used=None,
        equity=format_decimal(wallet.cash),
        unrealized_pnl=None,
        realized_pnl=format_decimal(wallet.total_realized_pnl),
        total_open_risk=None,
        open_position_count=len(repo.get_open_positions()),
    )


@app.get("/positions", response_model=PaginatedResponse)
def list_positions(
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
    items = [_position_response(p) for p in rows[:page_limit]]
    next_cursor = None
    if len(rows) > page_limit:
        last = rows[page_limit - 1]
        next_cursor = encode_cursor(
            {"opened_at": format_utc(last.opened_at), "position_id": str(last.position_id)}
        )
    return PaginatedResponse(items=items, next_cursor=next_cursor, limit=page_limit)


@app.get("/positions/{position_id}", response_model=PositionResponse)
def get_position(
    position_id: UUID,
    repo: Annotated[PaperTradingRepository, Depends(get_repository)],
) -> PositionResponse:
    position = repo.get_position(position_id)
    if position is None:
        raise HTTPException(status_code=404, detail="position not found")
    return _position_response(position)


@app.get("/intents", response_model=PaginatedResponse)
def list_intents(
    repo: Annotated[PaperTradingRepository, Depends(get_repository)],
    limit: Annotated[int, Query(ge=1)] = 50,
    cursor: str | None = None,
) -> PaginatedResponse:
    page_limit = parse_page_limit(limit)
    after_created_at: datetime | None = None
    after_intent_id: UUID | None = None
    if cursor:
        try:
            data = decode_cursor(cursor)
            after_created_at = datetime.fromisoformat(data["created_at"].replace("Z", "+00:00"))
            after_intent_id = UUID(data["intent_id"])
        except (KeyError, ValueError, TypeError) as exc:
            raise HTTPException(status_code=400, detail="invalid cursor") from exc
    rows = repo.list_intents(
        limit=page_limit + 1,
        after_created_at=after_created_at,
        after_intent_id=after_intent_id,
    )
    items = [
        IntentResponse(
            intent_id=format_uuid(i.intent_id),
            idempotency_key=i.idempotency_key,
            symbol=i.symbol,
            side=i.side.value,
            signal_type=i.signal_type.value,
            signal_time=format_utc(i.signal_time),
            scheduled_fill_time=format_utc(i.scheduled_fill_time),
            requested_entry=format_decimal(i.requested_entry),
            requested_stop=format_decimal(i.requested_stop),
            status=i.status.value,
            strategy_evaluation_id=format_uuid(i.strategy_evaluation_id),
            created_at=format_utc(i.created_at),
            updated_at=format_utc(i.updated_at),
        )
        for i in rows[:page_limit]
    ]
    next_cursor = None
    if len(rows) > page_limit:
        last = rows[page_limit - 1]
        next_cursor = encode_cursor(
            {"created_at": format_utc(last.created_at), "intent_id": str(last.intent_id)}
        )
    return PaginatedResponse(items=items, next_cursor=next_cursor, limit=page_limit)


@app.get("/orders", response_model=PaginatedResponse)
def list_orders(
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
        )
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


@app.get("/fills", response_model=PaginatedResponse)
def list_fills(
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
            fill_kind=f.fill_kind.value,
            paper_order_id=format_uuid(f.paper_order_id) if f.paper_order_id else None,
            position_id=format_uuid(f.position_id) if f.position_id else None,
            symbol=f.symbol,
            side=f.side.value,
            quantity=format_decimal(f.quantity),
            market_open_price=format_decimal(f.market_open_price),
            slippage=format_decimal(f.slippage),
            fill_price=format_decimal(f.fill_price),
            fee=format_decimal(f.fee),
            fill_time=format_utc(f.fill_time),
            candle_key=format_utc(f.candle_key),
            fill_sequence=f.fill_sequence,
            deterministic_fill_key=f.deterministic_fill_key,
        )
        for f in rows[:page_limit]
    ]
    next_cursor = None
    if len(rows) > page_limit:
        last = rows[page_limit - 1]
        next_cursor = encode_cursor(
            {"fill_time": format_utc(last.fill_time), "fill_id": str(last.fill_id)}
        )
    return PaginatedResponse(items=items, next_cursor=next_cursor, limit=page_limit)


@app.get("/evaluations", response_model=PaginatedResponse)
def list_evaluations(
    repo: Annotated[PaperTradingRepository, Depends(get_repository)],
    limit: Annotated[int, Query(ge=1)] = 50,
    cursor: str | None = None,
) -> PaginatedResponse:
    page_limit = parse_page_limit(limit)
    after_created_at: datetime | None = None
    after_evaluation_id: UUID | None = None
    if cursor:
        try:
            data = decode_cursor(cursor)
            after_created_at = datetime.fromisoformat(data["created_at"].replace("Z", "+00:00"))
            after_evaluation_id = UUID(data["evaluation_id"])
        except (KeyError, ValueError, TypeError) as exc:
            raise HTTPException(status_code=400, detail="invalid cursor") from exc
    rows = repo.list_evaluations(
        limit=page_limit + 1,
        after_created_at=after_created_at,
        after_evaluation_id=after_evaluation_id,
    )
    items = [
        EvaluationResponse(
            evaluation_id=format_uuid(e.evaluation_id),
            symbol=e.symbol,
            evaluation_time=format_utc(e.evaluation_time),
            daily_candle_open_time=format_utc(e.daily_candle_open_time),
            strategy_version=e.strategy_version,
            created_at=format_utc(e.created_at),
        )
        for e in rows[:page_limit]
    ]
    next_cursor = None
    if len(rows) > page_limit:
        last = rows[page_limit - 1]
        next_cursor = encode_cursor(
            {
                "created_at": format_utc(last.created_at),
                "evaluation_id": str(last.evaluation_id),
            }
        )
    return PaginatedResponse(items=items, next_cursor=next_cursor, limit=page_limit)


@app.get("/audit-events", response_model=PaginatedResponse)
def list_audit_events(
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
            cycle_id=format_uuid(e.cycle_id) if e.cycle_id else None,
            payload_json=_sanitize_payload(e.payload_json),
            created_at=format_utc(e.created_at),
        )
        for e in rows[:page_limit]
    ]
    next_cursor = None
    if len(rows) > page_limit:
        last = rows[page_limit - 1]
        next_cursor = encode_cursor(
            {"created_at": format_utc(last.created_at), "event_id": str(last.event_id)}
        )
    return PaginatedResponse(items=items, next_cursor=next_cursor, limit=page_limit)


@app.get("/scheduler-runs", response_model=PaginatedResponse)
def list_scheduler_runs(
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
        )
        for r in rows[:page_limit]
    ]
    next_cursor = None
    if len(rows) > page_limit:
        last = rows[page_limit - 1]
        next_cursor = encode_cursor(
            {"scheduled_for": format_utc(last.scheduled_for), "run_id": str(last.run_id)}
        )
    return PaginatedResponse(items=items, next_cursor=next_cursor, limit=page_limit)


@app.post("/control/pause", response_model=ControlResponse)
def control_pause(
    request: Request,
    repo: Annotated[PaperTradingRepository, Depends(get_repository)],
    _: Annotated[None, Depends(verify_control_api_key)],
) -> ControlResponse:
    runtime_svc = RuntimeService(repo)
    with transaction_scope(repo.session):
        runtime_svc.set_paused(True)
        _audit_control(repo, "CONTROL_PAUSE", request, accepted=True)
    return ControlResponse(accepted=True, message="paused")


@app.post("/control/resume", response_model=ControlResponse)
def control_resume(
    request: Request,
    repo: Annotated[PaperTradingRepository, Depends(get_repository)],
    _: Annotated[None, Depends(verify_control_api_key)],
) -> ControlResponse:
    runtime = repo.get_runtime_state()
    if runtime is None:
        raise HTTPException(status_code=503, detail="runtime missing")
    if runtime.kill_switch:
        _audit_control(repo, "CONTROL_RESUME_REJECTED", request, accepted=False)
        raise HTTPException(status_code=409, detail="kill switch active")
    if RecoveryService.is_recovery_active():
        raise HTTPException(status_code=409, detail="recovery active")
    runtime_svc = RuntimeService(repo)
    with transaction_scope(repo.session):
        runtime_svc.set_paused(False)
        _audit_control(repo, "CONTROL_RESUME", request, accepted=True)
    return ControlResponse(accepted=True, message="resumed")


@app.post("/control/kill", response_model=ControlResponse)
def control_kill(
    request: Request,
    repo: Annotated[PaperTradingRepository, Depends(get_repository)],
    _: Annotated[None, Depends(verify_control_api_key)],
    body: KillControlRequest | None = None,
) -> ControlResponse:
    if body is not None and body.close_policy == KillSwitchClosePolicy.CLOSE_AT_NEXT_OPEN.value:
        _audit_control(
            repo,
            "CONTROL_KILL_POLICY_REJECTED",
            request,
            accepted=False,
            extra={"close_policy": KillSwitchClosePolicy.CLOSE_AT_NEXT_OPEN.value},
        )
        raise HTTPException(
            status_code=422,
            detail=(
                "CLOSE_AT_NEXT_OPEN is not supported in paper trading V1; "
                "only KillSwitchClosePolicy.FREEZE is available"
            ),
        )
    runtime_svc = RuntimeService(repo)
    with transaction_scope(repo.session):
        runtime_svc.set_kill_switch(True)
        _audit_control(repo, "CONTROL_KILL", request, accepted=True)
    return ControlResponse(accepted=True, message="kill switch enabled")


@app.post("/control/recover", response_model=ControlResponse)
def control_recover(
    request: Request,
    repo: Annotated[PaperTradingRepository, Depends(get_repository)],
    config: Annotated[PaperTradingConfig, Depends(get_config)],
    _: Annotated[None, Depends(verify_control_api_key)],
) -> ControlResponse:
    if RecoveryService.is_recovery_active():
        raise HTTPException(status_code=409, detail="recovery already running")
    lock = _advisory_lock_for_recover(config, repo)
    state_lock = get_app_state().advisory_lock
    release_after = False
    if state_lock is not None and state_lock.held:
        active_lock = state_lock
    elif not lock.try_acquire():
        raise HTTPException(status_code=409, detail="advisory lock not available")
    else:
        active_lock = lock
        release_after = True
    try:
        runtime_svc = RuntimeService(repo)
        with transaction_scope(repo.session):
            runtime_svc.recover_on_startup(
                config,
                active_lock,
                market_data_ready=_market_data_ready(),
            )
            _audit_control(repo, "CONTROL_RECOVER", request, accepted=True)
    finally:
        if release_after:
            lock.release()
    return ControlResponse(accepted=True, message="recovery completed")


@app.post("/control/run-cycle", response_model=ControlResponse)
def control_run_cycle(
    body: RunCycleRequest,
    request: Request,
    repo: Annotated[PaperTradingRepository, Depends(get_repository)],
    config: Annotated[PaperTradingConfig, Depends(get_config)],
    _: Annotated[None, Depends(verify_control_api_key)],
) -> ControlResponse:
    if config.paper_production_mode:
        raise HTTPException(status_code=403, detail="run cycle disabled in production mode")
    try:
        scheduled_for = body.validate_scheduled_for()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if body.job_name not in {j.value for j in SchedulerJobName}:
        raise HTTPException(status_code=400, detail="unknown job name")
    key = scheduler_run_key(body.job_name, scheduled_for)
    created: bool
    with transaction_scope(repo.session):
        row = SchedulerRunRow(
            run_id=uuid4(),
            job_name=body.job_name,
            scheduled_for=scheduled_for,
            status=SchedulerRunStatus.COMPLETED.value,
            idempotency_key=key,
        )
        run, created = repo.insert_or_get_scheduler_run(row)
        _audit_control(
            repo,
            "CONTROL_RUN_CYCLE",
            request,
            accepted=True,
            extra={
                "job_name": body.job_name,
                "deduplicated": not created,
                "run_id": str(run.run_id),
            },
        )
    message = "scheduler run recorded" if created else "scheduler run deduplicated"
    return ControlResponse(accepted=True, message=message)


def _audit_control(
    repo: PaperTradingRepository,
    event_type: str,
    request: Request,
    *,
    accepted: bool,
    extra: dict[str, Any] | None = None,
) -> None:
    runtime = repo.get_runtime_state()
    if runtime is None:
        return
    payload: dict[str, Any] = {
        "accepted": accepted,
        "client_host": request.client.host if request.client else None,
        "path": str(request.url.path),
    }
    if extra:
        payload.update(extra)
    repo.append_audit_event(
        event_type=event_type,
        aggregate_type="runtime_state",
        aggregate_id=runtime.instance_id,
        payload_json=payload,
    )


def _sanitize_error(value: str | None) -> str | None:
    if value is None or not value.strip():
        return None
    lowered = value.lower()
    if "password" in lowered or "secret" in lowered or "key" in lowered:
        return "sanitized error"
    return value


def _sanitize_payload(payload: dict[str, Any]) -> dict[str, Any]:
    sanitized: dict[str, Any] = {}
    for key, value in payload.items():
        if key.lower() in {"api_key", "password", "secret", "database_url"}:
            sanitized[key] = "[redacted]"
        else:
            sanitized[key] = value
    return sanitized


@app.exception_handler(Exception)
def generic_exception_handler(_: Request, exc: Exception) -> JSONResponse:
    return JSONResponse(status_code=500, content={"detail": "internal error"})


def create_app() -> FastAPI:
    return app
