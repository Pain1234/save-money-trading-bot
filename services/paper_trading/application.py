"""Production application wiring for paper trading."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol

from alembic.config import Config
from alembic.script import ScriptDirectory
from market_data.repository import InMemoryCandleRepository
from market_data.runtime import HyperliquidMarketDataRuntime
from market_data.service import MarketDataService
from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from paper_trading.app_state import configure_app_state
from paper_trading.clock import Clock, SystemClock
from paper_trading.controlled_market_data import ControlledMarketDataRuntime
from paper_trading.db.session import create_db_engine, create_session_factory
from paper_trading.enums import RuntimeStatus
from paper_trading.lock import PostgresAdvisoryLock
from paper_trading.market_events import MarketEventBridge
from paper_trading.orchestrator import PaperTradingOrchestrator
from paper_trading.readiness import ReadinessService
from paper_trading.repository import PaperTradingRepository
from paper_trading.runtime import RuntimeService
from paper_trading.scheduler import PaperTradingScheduler, SchedulerJobName
from paper_trading.scheduler_context import ProductionContextBuilder
from paper_trading.service_config import PaperServiceConfig
from paper_trading.symbol_constraints import (
    HyperliquidSymbolConstraintsProvider,
    SymbolConstraintsProvider,
    load_constraints_provider,
)

logger = logging.getLogger(__name__)


class MarketDataRuntime(Protocol):
    async def start(self, evaluation_time: datetime) -> None: ...

    async def aclose(self) -> None: ...

    def status(self, evaluation_time: datetime) -> Any: ...

    async def process_live(self, evaluation_time: datetime) -> int: ...


@dataclass
class FakeMarketDataRuntime:
    """Deterministic market-data double for integration tests."""

    _ready: bool = False
    _closed: bool = False

    async def start(self, evaluation_time: datetime) -> None:
        self._ready = True

    async def aclose(self) -> None:
        self._closed = True
        self._ready = False

    async def process_live(self, evaluation_time: datetime) -> int:
        return 0

    def status(self, evaluation_time: datetime) -> Any:
        from market_data.config import HyperliquidNetwork
        from market_data.models import ConnectionStatus
        from market_data.runtime import HyperliquidRuntimeStatus

        return HyperliquidRuntimeStatus(
            network=HyperliquidNetwork.TESTNET,
            websocket_status=(
                ConnectionStatus.CONNECTED if self._ready else ConnectionStatus.DISCONNECTED
            ),
            subscriptions_expected=9,
            subscriptions_acknowledged=9 if self._ready else 0,
            readiness=self._ready and not self._closed,
        )

    @property
    def closed(self) -> bool:
        return self._closed


@dataclass
class PaperTradingApplication:
    """Coordinates DB, recovery, market data, scheduler, and optional API."""

    config: PaperServiceConfig
    clock: Clock = field(default_factory=SystemClock)
    market_data_runtime: MarketDataRuntime | None = None
    constraints_provider: SymbolConstraintsProvider | None = None
    alembic_config: Config | None = None
    event_poll_interval_seconds: float = 1.0

    _engine: Engine | None = field(default=None, init=False)
    _session_factory: sessionmaker[Session] | None = field(default=None, init=False)
    _session: Session | None = field(default=None, init=False)
    _repo: PaperTradingRepository | None = field(default=None, init=False)
    _advisory_lock: PostgresAdvisoryLock | None = field(default=None, init=False)
    _orchestrator: PaperTradingOrchestrator | None = field(default=None, init=False)
    _scheduler: PaperTradingScheduler | None = field(default=None, init=False)
    _runtime: RuntimeService | None = field(default=None, init=False)
    _md_runtime: MarketDataRuntime | None = field(default=None, init=False)
    _market_data_service: MarketDataService | None = field(default=None, init=False)
    _candle_repository: InMemoryCandleRepository | None = field(default=None, init=False)
    _event_bridge: MarketEventBridge | None = field(default=None, init=False)
    _constraints: SymbolConstraintsProvider | None = field(default=None, init=False)
    _tasks: list[asyncio.Task[Any]] = field(default_factory=list, init=False)
    _shutdown_event: asyncio.Event = field(default_factory=asyncio.Event, init=False)
    _started: bool = field(default=False, init=False)
    _last_loop_error: str | None = field(default=None, init=False)

    @property
    def repository(self) -> PaperTradingRepository:
        assert self._repo is not None
        return self._repo

    @property
    def scheduler(self) -> PaperTradingScheduler:
        assert self._scheduler is not None
        return self._scheduler

    @property
    def advisory_lock(self) -> PostgresAdvisoryLock:
        assert self._advisory_lock is not None
        return self._advisory_lock

    @property
    def market_data_service(self) -> MarketDataService | None:
        return self._market_data_service

    @property
    def candle_repository(self) -> InMemoryCandleRepository | None:
        return self._candle_repository

    @property
    def event_bridge(self) -> MarketEventBridge | None:
        return self._event_bridge

    @property
    def controlled_market_data(self) -> ControlledMarketDataRuntime | None:
        if isinstance(self._md_runtime, ControlledMarketDataRuntime):
            return self._md_runtime
        return None

    @property
    def is_started(self) -> bool:
        return self._started

    @property
    def background_tasks(self) -> tuple[asyncio.Task[Any], ...]:
        return tuple(self._tasks)

    @property
    def database_engine(self) -> Engine | None:
        return self._engine

    def market_data_ready(self) -> bool:
        if self._md_runtime is None:
            return False
        status = self._md_runtime.status(self.clock.now())
        return bool(status.readiness)

    async def start(self) -> None:
        if self._started:
            return

        self._engine = create_db_engine(str(self.config.database_url))
        self._session_factory = create_session_factory(self._engine)
        self._session = self._session_factory()
        self._repo = PaperTradingRepository(self._session)
        self._runtime = RuntimeService(self._repo, clock=self.clock)
        self._advisory_lock = PostgresAdvisoryLock(self._engine, self.config.advisory_lock_id)

        self._verify_database()
        self._verify_migration_head()

        if not self._advisory_lock.try_acquire():
            raise RuntimeError("postgres advisory lock not available")

        recovery = self._runtime.recover_on_startup(
            self.config,
            self._advisory_lock,
            market_data_ready=False,
            db_engine=self._engine,
            alembic_config=self._alembic_config(),
        )
        if recovery.final_status == RuntimeStatus.FAILED:
            raise RuntimeError(f"recovery failed: {recovery.issues}")

        self._constraints = self.constraints_provider or load_constraints_provider(self.config)
        self._md_runtime = self._build_market_data_runtime()
        await self._md_runtime.start(self.clock.now())
        self._bootstrap_constraints_from_runtime()

        max_attempts = int(self.config.market_data_startup_timeout_seconds / 0.25) + 1
        attempts = 0
        while not self.market_data_ready():
            attempts += 1
            if attempts > max_attempts:
                raise TimeoutError("market data runtime did not become ready")
            await asyncio.sleep(0.25)
            await self._poll_market_data()

        self._orchestrator = PaperTradingOrchestrator(self._repo, self.config, clock=self.clock)
        self._scheduler = self._orchestrator.scheduler
        self._scheduler._market_data_ready = self.market_data_ready  # noqa: SLF001
        self._scheduler.set_jobs_enabled(True)

        if self._candle_repository is not None and self._market_data_service is not None:
            assert self._constraints is not None
            context_builder = ProductionContextBuilder(
                market_data=self._market_data_service,
                repository=self._repo,
                config=self.config,
                constraints=self._constraints,
                clock=self.clock,
                market_data_ready=self.market_data_ready,
            )
            self._event_bridge = MarketEventBridge(
                repository=self._repo,
                candle_repository=self._candle_repository,
                scheduler=self._scheduler,
                context_builder=context_builder,
                config=self.config,
                clock=self.clock,
                advisory_lock=self._advisory_lock,
                market_data_ready=self.market_data_ready,
            )

        configure_app_state(
            market_data_ready=self.market_data_ready,
            advisory_lock=self._advisory_lock,
            scheduler_active=True,
        )

        if self.config.api_enabled:
            self._start_api_server()

        self._tasks.append(asyncio.create_task(self._heartbeat_loop(), name="paper-heartbeat"))
        self._tasks.append(asyncio.create_task(self._scheduler_loop(), name="paper-scheduler"))

        self._update_runtime_readiness()
        self._runtime.heartbeat()
        self._started = True
        logger.info("paper_trading_application_started")

    async def stop(self) -> None:
        if not self._started:
            return
        self._shutdown_event.set()
        if self._scheduler is not None:
            self._scheduler.set_jobs_enabled(False)
        if self._runtime is not None:
            self._runtime.transition(RuntimeStatus.SHUTTING_DOWN)

        for task in self._tasks:
            task.cancel()
        if self._tasks:
            results = await asyncio.gather(*self._tasks, return_exceptions=True)
            for result in results:
                if isinstance(result, Exception) and not isinstance(result, asyncio.CancelledError):
                    logger.exception("task_shutdown_error", exc_info=result)

        self._tasks.clear()

        if self._md_runtime is not None:
            await self._md_runtime.aclose()

        if self._advisory_lock is not None:
            self._advisory_lock.release()

        if self._session is not None:
            self._session.close()
            self._session = None
        if self._engine is not None:
            self._engine.dispose()
            self._engine = None

        if self._runtime is not None:
            state = self._runtime.get_state()
            if state.status == RuntimeStatus.SHUTTING_DOWN:
                self._runtime.transition(RuntimeStatus.STOPPED)

        configure_app_state(scheduler_active=False)
        self._started = False
        logger.info("paper_trading_application_stopped")

    def _build_market_data_runtime(self) -> MarketDataRuntime:
        if self.market_data_runtime is not None:
            if isinstance(self.market_data_runtime, ControlledMarketDataRuntime):
                self._market_data_service = self.market_data_runtime.service
                self._candle_repository = self.market_data_runtime.repository
            elif isinstance(self.market_data_runtime, HyperliquidMarketDataRuntime):
                self._market_data_service = self.market_data_runtime._service  # noqa: SLF001
                self._candle_repository = self.market_data_runtime.repository
            return self.market_data_runtime
        repo = InMemoryCandleRepository()
        service = MarketDataService(repo)
        self._market_data_service = service
        self._candle_repository = repo
        return HyperliquidMarketDataRuntime(service, self.config.hyperliquid_public_config())

    def _bootstrap_constraints_from_runtime(self) -> None:
        if self._constraints is not None:
            return
        if isinstance(self._md_runtime, HyperliquidMarketDataRuntime):
            sz = self._md_runtime._meta_cache.get_sz_decimals()  # noqa: SLF001
            if sz:
                self._constraints = HyperliquidSymbolConstraintsProvider(sz)
                missing = [s for s in self.config.symbols if self._constraints.get(s) is None]
                if missing:
                    raise RuntimeError(
                        f"missing SymbolConstraints from Hyperliquid meta: {missing}"
                    )
                return
        raise RuntimeError(
            "SymbolConstraints unavailable: set PAPER_SYMBOL_CONSTRAINTS_JSON "
            "or use Hyperliquid meta"
        )

    def _alembic_config(self) -> Config:
        if self.alembic_config is not None:
            return self.alembic_config
        import os

        root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
        cfg = Config(os.path.join(root, "alembic.ini"))
        cfg.set_main_option("sqlalchemy.url", str(self.config.database_url))
        return cfg

    def _verify_database(self) -> None:
        assert self._engine is not None
        with self._engine.connect() as conn:
            conn.execute(text("SELECT 1"))

    def _verify_migration_head(self) -> None:
        cfg = self._alembic_config()
        script = ScriptDirectory.from_config(cfg)
        head = script.get_current_head()
        assert self._engine is not None
        with self._engine.connect() as conn:
            current = conn.execute(
                text("SELECT version_num FROM alembic_version LIMIT 1")
            ).scalar_one_or_none()
        if current != head:
            raise RuntimeError(f"migration not at head: current={current} head={head}")

    async def _poll_market_data(self) -> None:
        if self._md_runtime is None:
            return
        await self._md_runtime.process_live(self.clock.now())

    def _process_committed_market_event_poll(self, evaluation_time: datetime) -> None:
        """Run one market-event poll with a single outer commit/rollback boundary."""
        assert self._event_bridge is not None
        assert self._repo is not None
        try:
            poll_result = self._event_bridge.process_after_poll(evaluation_time)
            for outcome in poll_result.outcomes:
                if outcome.deferred or outcome.retryable:
                    continue
                if outcome.status.name == "FAILED":
                    self._last_loop_error = outcome.error
            if poll_result.permanent_failures:
                self._last_loop_error = poll_result.permanent_failures[0].error
            self._repo.session.commit()
        except Exception:
            self._repo.session.rollback()
            raise
        else:
            self._event_bridge.acknowledge_committed(poll_result.events_to_ack)
            self._event_bridge.acknowledge_terminal_failed_committed(
                poll_result.events_terminal_failed
            )

    def _update_runtime_readiness(self) -> None:
        assert self._runtime is not None
        assert self._repo is not None
        readiness = ReadinessService(
            self._repo,
            self.config,
            clock=self.clock,
            db_engine=self._engine,
            alembic_config=self._alembic_config(),
        )
        bridge = self._event_bridge
        bridge_overflow = bridge is not None and bridge.queue_overflow
        bridge_backlog = bridge is not None and bridge.has_event_backlog
        bridge_permanent = bridge is not None and bridge.has_permanent_failures
        snapshot = readiness.evaluate(
            market_data_ready=self.market_data_ready() and not bridge_overflow,
            advisory_lock=self._advisory_lock,
            scheduler_active=self._scheduler is not None and self._scheduler.jobs_enabled,
        )
        runtime_ready = snapshot.runtime_readiness and not bridge_backlog
        state = self._runtime.get_state()
        if runtime_ready and not bridge_permanent and state.status in {
            RuntimeStatus.RECOVERING,
            RuntimeStatus.DEGRADED,
            RuntimeStatus.STARTING,
        }:
            self._runtime.transition(RuntimeStatus.READY, last_error="")
        elif (not runtime_ready or bridge_permanent) and state.status == RuntimeStatus.READY:
            if bridge_permanent:
                reason = "permanent_configuration_failure"
            elif bridge_backlog:
                if bridge is not None and bridge.deferred_events:
                    reason = "deferred_market_events"
                elif bridge_overflow:
                    reason = "event_queue_overflow"
                else:
                    reason = "event_backlog"
            else:
                reason = ",".join(snapshot.reasons) or self._last_loop_error or "not_ready"
            self._runtime.transition(RuntimeStatus.DEGRADED, last_error=reason)

    async def _heartbeat_loop(self) -> None:
        assert self._scheduler is not None
        while not self._shutdown_event.is_set():
            try:
                if self.market_data_ready() and self._advisory_lock is not None:
                    if self._advisory_lock.try_acquire() or self._advisory_lock.held:
                        self._scheduler.run_job(
                            SchedulerJobName.RUNTIME_HEARTBEAT,
                            scheduled_for=self.clock.now(),
                        )
                await asyncio.sleep(self.config.heartbeat_interval_seconds)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("heartbeat_loop_error")
                await asyncio.sleep(1)

    async def _scheduler_loop(self) -> None:
        while not self._shutdown_event.is_set():
            try:
                await self._poll_market_data()
                evaluation_time = self.clock.now()

                if (
                    self._event_bridge is not None
                    and self._advisory_lock is not None
                    and self._repo is not None
                ):
                    if self._advisory_lock.held and self.market_data_ready():
                        self._process_committed_market_event_poll(evaluation_time)

                self._update_runtime_readiness()
                await asyncio.sleep(self.event_poll_interval_seconds)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self._last_loop_error = str(exc)
                logger.exception("scheduler_loop_error")
                await asyncio.sleep(1)

    def _start_api_server(self) -> None:
        import uvicorn

        config = uvicorn.Config(
            "paper_trading.api:app",
            host=self.config.api_host,
            port=self.config.api_port,
            log_level="info",
        )
        server = uvicorn.Server(config)
        self._tasks.append(asyncio.create_task(server.serve(), name="paper-api"))
