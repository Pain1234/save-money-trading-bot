"""Robustness orchestration write service (Issue #247 / P4.7b).

Creates/starts/status-polls robustness test suites that run the P5 helper
outputs through the SAME research runner/registry/artifact line as regular
Strategy Lab experiments (Issue #242) — no second backtest engine. Only
``walk_forward`` / ``cost_stress`` / ``parameter_stability`` execute child
runs via :func:`research.runner.run_experiment`; ``bootstrap`` post-processes
an already-completed run's ``equity.json`` artifact (no child runs).
"""

from __future__ import annotations

import json
import logging
import os
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any

from backtester.models import HistoricalDataBundle

from research.artifacts import load_checksums
from research.experiment_spec import load_experiment_spec
from research.jobs import get_worker_id, lease_seconds_from_env
from research.registry import ExperimentRegistry, RegistryEntry
from research.robustness import (
    ROBUSTNESS_MANIFEST_SCHEMA_VERSION,
    ROBUSTNESS_TEST_TYPES,
    RobustnessChildResult,
    RobustnessChildSpec,
    RobustnessManifest,
    build_cost_stress_child_specs,
    build_parameter_stability_child_specs,
    build_walk_forward_child_specs,
    compute_bootstrap_from_equity_artifact,
    compute_robustness_id,
    load_robustness_manifest,
    save_robustness_manifest,
)
from research.robustness_jobs import (
    RobustnessJob,
    RobustnessJobStore,
    RobustnessJobTransitionError,
    _utc_now,
)
from research.runner import RunRequest, run_experiment
from research.service import assert_safe_id
from research.walk_forward import DEFAULT_FEATURE_WARMUP_MONTHLY_BARS
from research.write_service import (
    DatasetCatalogEntry,
    ResearchWriteError,
    load_dataset_catalog,
    repo_root_from_env,
)

logger = logging.getLogger(__name__)


class RobustnessNotFoundError(KeyError):
    """No completed registry entry for the requested base_experiment_id."""


class RobustnessBaseRunError(RuntimeError):
    """Pinned base run missing, incomplete, or checksum-failed (fail-closed)."""


def _latest_complete_entry(
    registry: ExperimentRegistry,
    experiment_id: str,
    *,
    run_id: str | None = None,
) -> RegistryEntry:
    candidates = [
        e
        for e in registry.list_entries()
        if e.experiment_id == experiment_id
        and e.status == "complete"
        and (run_id is None or e.run_id == run_id)
    ]
    if not candidates:
        msg = f"no complete run found for experiment_id={experiment_id!r}"
        raise RobustnessNotFoundError(msg)
    return candidates[-1]


def _load_pinned_base_entry(
    registry: ExperimentRegistry,
    *,
    base_experiment_id: str,
    base_run_id: str,
) -> RegistryEntry:
    """Load the exact registry entry pinned on the job; verify checksums.

    Never falls back to ``_latest_complete_entry`` — a newer complete run for
    the same experiment must not silently replace the pinned base (Issue #247 P1).
    """
    try:
        entry = registry.show(base_run_id, verify=True)
    except KeyError as exc:
        msg = f"pinned base run missing: run_id={base_run_id!r}"
        raise RobustnessBaseRunError(msg) from exc
    except (OSError, ValueError) as exc:
        msg = (
            f"pinned base run checksum verification failed: "
            f"run_id={base_run_id!r}: {exc}"
        )
        raise RobustnessBaseRunError(msg) from exc
    if entry.experiment_id != base_experiment_id:
        msg = (
            f"pinned base run experiment mismatch: "
            f"expected {base_experiment_id!r}, found {entry.experiment_id!r}"
        )
        raise RobustnessBaseRunError(msg)
    if entry.status != "complete":
        msg = (
            f"pinned base run is not complete: "
            f"run_id={base_run_id!r} status={entry.status!r}"
        )
        raise RobustnessBaseRunError(msg)
    return entry


class RobustnessOrchestrationService:
    def __init__(
        self,
        root: Path,
        *,
        repo_root: Path | None = None,
        allow_dirty_git: bool | None = None,
    ) -> None:
        self.root = root.resolve()
        self.repo_root = (repo_root or repo_root_from_env()).resolve()
        self.store = RobustnessJobStore(self.root)
        self.registry = ExperimentRegistry(self.root)
        if allow_dirty_git is None:
            allow_dirty_git = os.environ.get("RESEARCH_ALLOW_DIRTY_GIT", "").strip() in {
                "1",
                "true",
                "TRUE",
                "yes",
            }
        self.allow_dirty_git = bool(allow_dirty_git)

    @staticmethod
    def _normalize_config(test_type: str, raw: Any) -> dict[str, Any]:
        if not isinstance(raw, dict):
            raw = {}

        if test_type == "walk_forward":
            try:
                n_folds = int(raw.get("n_folds", 3))
                embargo_days = int(raw.get("embargo_days", 90))
                feature_warmup_monthly_bars = int(
                    raw.get(
                        "feature_warmup_monthly_bars",
                        DEFAULT_FEATURE_WARMUP_MONTHLY_BARS,
                    )
                )
            except (TypeError, ValueError) as exc:
                raise ResearchWriteError(
                    "config ungültig", field_errors={"config": str(exc)}
                ) from exc
            if n_folds < 1:
                raise ResearchWriteError(
                    "n_folds muss >= 1 sein",
                    field_errors={"config.n_folds": "muss >= 1 sein"},
                )
            if embargo_days < 0:
                raise ResearchWriteError(
                    "embargo_days darf nicht negativ sein",
                    field_errors={"config.embargo_days": "muss >= 0 sein"},
                )
            if feature_warmup_monthly_bars < 1:
                raise ResearchWriteError(
                    "feature_warmup_monthly_bars muss >= 1 sein",
                    field_errors={
                        "config.feature_warmup_monthly_bars": "muss >= 1 sein"
                    },
                )
            return {
                "n_folds": n_folds,
                "embargo_days": embargo_days,
                "feature_warmup_monthly_bars": feature_warmup_monthly_bars,
            }

        if test_type == "cost_stress":
            return {}

        if test_type == "parameter_stability":
            out: dict[str, Any] = {}
            int_deltas = raw.get("int_deltas")
            if int_deltas is not None:
                out["int_deltas"] = {
                    str(key): tuple(int(v) for v in values)
                    for key, values in dict(int_deltas).items()
                }
            decimal_steps = raw.get("decimal_relative_steps")
            if decimal_steps is not None:
                out["decimal_relative_steps"] = {
                    str(key): tuple(str(v) for v in values)
                    for key, values in dict(decimal_steps).items()
                }
            return out

        if test_type == "bootstrap":
            try:
                block_length = int(raw.get("block_length", 5))
                n_simulations = int(raw.get("n_simulations", 1000))
                seed = int(raw.get("seed", 42))
                quantiles = tuple(float(q) for q in raw.get("quantiles") or (0.05, 0.5, 0.95))
            except (TypeError, ValueError) as exc:
                raise ResearchWriteError(
                    "config ungültig", field_errors={"config": str(exc)}
                ) from exc
            if block_length < 1:
                raise ResearchWriteError(
                    "block_length muss >= 1 sein",
                    field_errors={"config.block_length": "muss >= 1 sein"},
                )
            if n_simulations < 1:
                raise ResearchWriteError(
                    "n_simulations muss >= 1 sein",
                    field_errors={"config.n_simulations": "muss >= 1 sein"},
                )
            return {
                "block_length": block_length,
                "n_simulations": n_simulations,
                "seed": seed,
                "quantiles": list(quantiles),
            }

        raise ResearchWriteError(
            "unbekannter Robustheitstest", field_errors={"test_type": "unbekannt"}
        )

    def create(self, payload: dict[str, Any]) -> dict[str, Any]:
        test_type = str(payload.get("test_type") or "").strip()
        if test_type not in ROBUSTNESS_TEST_TYPES:
            raise ResearchWriteError(
                "unbekannter Robustheitstest",
                field_errors={
                    "test_type": f"muss einer von {', '.join(ROBUSTNESS_TEST_TYPES)} sein"
                },
            )

        base_experiment_id_raw = str(payload.get("base_experiment_id") or "").strip()
        if not base_experiment_id_raw:
            raise ResearchWriteError(
                "base_experiment_id ist erforderlich",
                field_errors={"base_experiment_id": "erforderlich"},
            )
        try:
            base_experiment_id = assert_safe_id(
                base_experiment_id_raw, field="base_experiment_id"
            )
        except ValueError as exc:
            raise ResearchWriteError(
                str(exc), field_errors={"base_experiment_id": str(exc)}
            ) from exc

        base_run_id_raw = payload.get("base_run_id")
        base_run_id = str(base_run_id_raw).strip() if base_run_id_raw else None

        try:
            entry = _latest_complete_entry(
                self.registry, base_experiment_id, run_id=base_run_id
            )
        except RobustnessNotFoundError as exc:
            raise ResearchWriteError(
                "Kein abgeschlossener Lauf für base_experiment_id gefunden",
                field_errors={"base_experiment_id": str(exc)},
            ) from exc

        dataset_catalog_id = str(payload.get("dataset_catalog_id") or "").strip() or None
        if test_type != "bootstrap":
            catalog = {e.id: e for e in load_dataset_catalog()}
            if not dataset_catalog_id or dataset_catalog_id not in catalog:
                raise ResearchWriteError(
                    "Dataset-Katalog-Eintrag fehlt oder ist unbekannt "
                    "(kein freier Dateipfad erlaubt)",
                    field_errors={"dataset_catalog_id": "unbekannt"},
                )

        config = self._normalize_config(test_type, payload.get("config"))

        robustness_id = compute_robustness_id(
            base_experiment_id=base_experiment_id,
            test_type=test_type,
            config=config,
            dataset_catalog_id=dataset_catalog_id,
            base_run_id=entry.run_id,
        )

        with self.store.lock_for(robustness_id):
            existing = self.store.get(robustness_id)
            if existing is not None:
                existing = self.store.mark_stale_if_needed(existing)
                if existing.status in {"queued", "running"}:
                    raise ResearchWriteError(
                        "Robustheitstest läuft bereits",
                        field_errors={"robustness_id": "Doppelstart verhindert"},
                    )
                if existing.status in {"completed", "failed"}:
                    return {
                        "robustness_id": robustness_id,
                        "status": existing.status,
                        "job": existing.to_dict(),
                        "base_run_id": existing.base_run_id,
                        "already_exists": True,
                    }

            now = _utc_now()
            job = RobustnessJob(
                robustness_id=robustness_id,
                base_experiment_id=base_experiment_id,
                base_run_id=entry.run_id,
                test_type=test_type,
                status="created",
                created_at=existing.created_at if existing else now,
                updated_at=now,
                dataset_catalog_id=dataset_catalog_id,
                config=config,
            )
            self.store.save(job)
            return {
                "robustness_id": robustness_id,
                "status": job.status,
                "job": job.to_dict(),
                "base_run_id": entry.run_id,
                "already_exists": False,
            }

    def _dispatch(self, robustness_id: str) -> None:
        """Start the in-process worker thread for a ``queued`` robustness job."""
        thread = threading.Thread(
            target=self._run_job,
            args=(robustness_id,),
            name=f"robustness-job-{robustness_id[:16]}",
            daemon=True,
        )
        self.store.register_thread(robustness_id, thread)
        thread.start()

    def recover_orphans(self) -> dict[str, list[str]]:
        """Startup recovery hook (Issue #245/#247).

        Re-dispatches orphaned ``queued`` suites; fails closed dead ``running``
        leases. If a re-queued suite cannot be re-dispatched (missing catalog
        for a non-bootstrap test), fail it closed rather than leave it stuck.
        """
        changed = self.store.recover_orphans()
        catalog = {e.id: e for e in load_dataset_catalog()}
        redispatched: list[str] = []
        failed_closed: list[str] = [
            job.robustness_id for job in changed if job.status == "failed"
        ]

        for job in changed:
            if job.status != "queued":
                continue
            if job.test_type != "bootstrap":
                if not job.dataset_catalog_id or job.dataset_catalog_id not in catalog:
                    reason = (
                        "Dataset-Katalog-Eintrag beim Restart-Recovery nicht auflösbar"
                    )

                    def _mutate(j: RobustnessJob, _reason: str = reason) -> None:
                        j.status = "failed"
                        j.finished_at = _utc_now()
                        j.updated_at = j.finished_at
                        j.error = _reason
                        j.error_detail = (
                            "V1 limitation: orphaned queued robustness job could not "
                            "be redispatched after restart."
                        )

                    try:
                        self.store.compare_and_set(
                            job.robustness_id,
                            expected_status="queued",
                            mutate=_mutate,
                        )
                    except RobustnessJobTransitionError:
                        pass
                    failed_closed.append(job.robustness_id)
                    continue
            self._dispatch(job.robustness_id)
            redispatched.append(job.robustness_id)

        if redispatched or failed_closed:
            logger.info(
                "robustness_job_recovery redispatched=%s failed_closed=%s",
                redispatched,
                failed_closed,
            )
        return {"redispatched": redispatched, "failed_closed": failed_closed}

    def start(self, robustness_id: str) -> dict[str, Any]:
        robustness_id = assert_safe_id(robustness_id, field="robustness_id")
        job_probe = self.store.get(robustness_id)
        if job_probe is None:
            raise KeyError(robustness_id)
        self.store.mark_stale_if_needed(job_probe)

        def _to_queued(job: RobustnessJob) -> None:
            job.status = "queued"
            job.updated_at = _utc_now()
            job.error = None
            job.error_detail = None
            job.finished_at = None
            job.started_at = None
            job.worker_id = None
            job.lease_id = None
            job.lease_expires_at = None

        try:
            job = self.store.compare_and_set(
                robustness_id, expected_status="created", mutate=_to_queued
            )
        except RobustnessJobTransitionError as exc:
            current = exc.current_status
            if current in {"queued", "running"}:
                raise ResearchWriteError(
                    "Robustheitstest läuft bereits oder ist in der Warteschlange",
                    field_errors={"status": "Doppelstart verhindert"},
                ) from exc
            raise ResearchWriteError(
                "Nur Tests im Status created können gestartet werden "
                "(kein Re-run in V1)",
                field_errors={"status": f"Aktueller Status: {current}"},
            ) from exc

        self._dispatch(robustness_id)

        refreshed = self.store.get(robustness_id)
        return {
            "robustness_id": robustness_id,
            "status": "queued",
            "job": (refreshed or job).to_dict(),
        }

    def get_status(self, robustness_id: str) -> dict[str, Any]:
        robustness_id = assert_safe_id(robustness_id, field="robustness_id")
        job = self.store.get(robustness_id)
        if job is None:
            raise KeyError(robustness_id)
        job = self.store.mark_stale_if_needed(job)
        elapsed: float | None = None
        if job.started_at:
            try:
                from datetime import UTC, datetime

                started = datetime.fromisoformat(job.started_at.replace("Z", "+00:00"))
                end = (
                    datetime.fromisoformat(job.finished_at.replace("Z", "+00:00"))
                    if job.finished_at
                    else datetime.now(UTC)
                )
                elapsed = max(0.0, (end - started).total_seconds())
            except ValueError:
                elapsed = None
        return {
            "robustness_id": robustness_id,
            "status": job.status,
            "test_type": job.test_type,
            "base_experiment_id": job.base_experiment_id,
            "base_run_id": job.base_run_id,
            "started_at": job.started_at,
            "finished_at": job.finished_at,
            "elapsed_seconds": elapsed,
            "error": job.error,
            "error_detail": job.error_detail,
            "job": job.to_dict(),
            "worker_alive": self.store.is_active(robustness_id),
        }

    def list_jobs(self, *, base_experiment_id: str | None = None) -> list[dict[str, Any]]:
        jobs = [self.store.mark_stale_if_needed(j) for j in self.store.list_jobs()]
        if base_experiment_id:
            jobs = [j for j in jobs if j.base_experiment_id == base_experiment_id]
        jobs.sort(key=lambda j: j.created_at, reverse=True)
        return [j.to_dict() for j in jobs]

    def get_manifest(self, robustness_id: str) -> dict[str, Any] | None:
        robustness_id = assert_safe_id(robustness_id, field="robustness_id")
        return load_robustness_manifest(self.root, robustness_id)

    def _load_bundle(self, bundle_path_raw: str) -> HistoricalDataBundle:
        bundle_path = Path(bundle_path_raw)
        if not bundle_path.is_absolute():
            bundle_path = (self.repo_root / bundle_path).resolve()
        try:
            bundle_path.relative_to(self.repo_root)
        except ValueError:
            try:
                bundle_path.relative_to(self.root)
            except ValueError as exc:
                msg = "bundle path escapes allowed roots"
                raise PermissionError(msg) from exc
        return HistoricalDataBundle.model_validate(
            json.loads(bundle_path.read_text(encoding="utf-8"))
        )

    def _run_child(
        self, child: RobustnessChildSpec, bundle: HistoricalDataBundle
    ) -> RobustnessChildResult:
        outcome = run_experiment(
            RunRequest(
                spec=child.spec,
                bundle=bundle,
                artifacts_root=self.root,
                repo_root=self.repo_root,
                allow_dirty_git=self.allow_dirty_git,
            )
        )
        if outcome.status == "complete" and outcome.artifact_path is not None:
            metrics_path = outcome.artifact_path / "metrics.json"
            metrics: dict[str, Any] = {}
            if metrics_path.is_file():
                metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
            costs_path = outcome.artifact_path / "costs.json"
            cost_ver = "1.0"
            if costs_path.is_file():
                costs = json.loads(costs_path.read_text(encoding="utf-8"))
                cost_ver = str(costs.get("cost_model_version", "1.0"))
            self.registry.register_complete(
                experiment_id=outcome.experiment_id,
                run_id=outcome.run_id,
                attempt_id=outcome.attempt_id,
                strategy_version=child.spec.strategy_version,
                dataset_version=child.spec.dataset_manifest_ref.dataset_id,
                cost_model_version=cost_ver,
                benchmark_ref=child.spec.benchmark,
                artifact_path=outcome.artifact_path,
                checksums=load_checksums(outcome.artifact_path),
            )
            return RobustnessChildResult(
                child_id=child.child_id,
                label=child.label,
                experiment_id=outcome.experiment_id,
                run_id=outcome.run_id,
                status="complete",
                net_pnl=(
                    str(metrics["net_pnl"]) if metrics.get("net_pnl") is not None else None
                ),
                max_drawdown=(
                    str(metrics["max_drawdown"])
                    if metrics.get("max_drawdown") is not None
                    else None
                ),
                closed_trades=(
                    int(metrics["closed_trades"])
                    if metrics.get("closed_trades") is not None
                    else None
                ),
                profit_factor=(
                    str(metrics["profit_factor"])
                    if metrics.get("profit_factor") is not None
                    else None
                ),
                error=None,
            )
        return RobustnessChildResult(
            child_id=child.child_id,
            label=child.label,
            experiment_id=outcome.experiment_id or None,
            run_id=outcome.run_id or None,
            status="failed",
            error=outcome.error or f"Run status: {outcome.status}",
        )

    def _build_child_specs(
        self, test_type: str, base_spec: Any, config: dict[str, Any]
    ) -> list[RobustnessChildSpec]:
        if test_type == "walk_forward":
            return build_walk_forward_child_specs(
                base_spec,
                n_folds=int(config["n_folds"]),
                embargo_days=int(config["embargo_days"]),
                feature_warmup_monthly_bars=int(config["feature_warmup_monthly_bars"]),
            )
        if test_type == "cost_stress":
            return build_cost_stress_child_specs(base_spec)
        return build_parameter_stability_child_specs(
            base_spec,
            int_deltas=config.get("int_deltas"),
            decimal_relative_steps=config.get("decimal_relative_steps"),
        )

    def _heartbeat_loop(
        self,
        robustness_id: str,
        worker_id: str,
        lease_id: str,
        stop_event: threading.Event,
        lease_seconds: int,
    ) -> None:
        """Lease renewal while the worker owns the robustness job."""
        interval = max(1.0, lease_seconds / 3)
        while not stop_event.wait(interval):
            try:
                self.store.renew_lease(
                    robustness_id,
                    worker_id=worker_id,
                    lease_id=lease_id,
                    lease_seconds=lease_seconds,
                )
            except (KeyError, RobustnessJobTransitionError):
                return

    def _run_job(self, robustness_id: str) -> None:
        worker_id = get_worker_id()
        lease_seconds = lease_seconds_from_env()
        try:
            job = self.store.claim(
                robustness_id, worker_id=worker_id, lease_seconds=lease_seconds
            )
        except RobustnessJobTransitionError:
            return
        lease_id = job.lease_id
        if lease_id is None:  # defensive; claim() always sets it
            return

        stop_heartbeat = threading.Event()
        heartbeat_thread = threading.Thread(
            target=self._heartbeat_loop,
            args=(robustness_id, worker_id, lease_id, stop_heartbeat, lease_seconds),
            name=f"robustness-job-lease-{robustness_id[:16]}",
            daemon=True,
        )
        heartbeat_thread.start()

        def _finish_owned(mutate: Callable[[RobustnessJob], None]) -> None:
            try:
                self.store.finish(
                    robustness_id,
                    worker_id=worker_id,
                    lease_id=lease_id,
                    mutate=mutate,
                )
            except (KeyError, RobustnessJobTransitionError):
                logger.warning(
                    "robustness_job_terminal_write_rejected robustness_id=%s "
                    "worker_id=%s lease_id=%s (stale owner; job already "
                    "reassigned or recovered)",
                    robustness_id,
                    worker_id,
                    lease_id,
                )

        try:
            job = self.store.get(robustness_id)
            assert job is not None
            config = dict(job.config or {})

            entry = _load_pinned_base_entry(
                self.registry,
                base_experiment_id=job.base_experiment_id,
                base_run_id=job.base_run_id,
            )
            base_spec = load_experiment_spec(Path(entry.artifact_path) / "experiment.json")

            children: list[RobustnessChildResult] = []
            bootstrap_result: dict[str, Any] | None = None

            if job.test_type == "bootstrap":
                quantiles = tuple(float(q) for q in config.get("quantiles", (0.05, 0.5, 0.95)))
                stats = compute_bootstrap_from_equity_artifact(
                    Path(entry.artifact_path),
                    block_length=int(config["block_length"]),
                    n_simulations=int(config["n_simulations"]),
                    seed=int(config["seed"]),
                    quantiles=quantiles,
                )
                bootstrap_result = {
                    "n_simulations": stats.n_simulations,
                    "block_length": stats.block_length,
                    "seed": stats.seed,
                    "net_pnl_quantiles": stats.net_pnl_quantiles,
                    "max_drawdown_quantiles": stats.max_drawdown_quantiles,
                    "mean_net_pnl": stats.mean_net_pnl,
                    "mean_max_drawdown": stats.mean_max_drawdown,
                }
                children = [
                    RobustnessChildResult(
                        child_id="bootstrap_source",
                        label="base run PnL series",
                        experiment_id=entry.experiment_id,
                        run_id=entry.run_id,
                        status="complete",
                    )
                ]
            else:
                catalog: dict[str, DatasetCatalogEntry] = {
                    e.id: e for e in load_dataset_catalog()
                }
                catalog_entry = catalog[str(job.dataset_catalog_id)]
                bundle = self._load_bundle(catalog_entry.bundle_path)
                child_specs = self._build_child_specs(job.test_type, base_spec, config)
                for child in child_specs:
                    try:
                        children.append(self._run_child(child, bundle))
                    except Exception as child_exc:  # noqa: BLE001
                        # One failing neighbor/scenario must not abort the whole suite.
                        children.append(
                            RobustnessChildResult(
                                child_id=child.child_id,
                                label=child.label,
                                experiment_id=None,
                                run_id=None,
                                status="failed",
                                error=str(child_exc),
                            )
                        )

            n_complete = sum(1 for c in children if c.status == "complete")
            n_failed = len(children) - n_complete
            summary = {
                "n_children": len(children),
                "n_complete": n_complete,
                "n_failed": n_failed,
            }
            manifest = RobustnessManifest(
                schema_version=ROBUSTNESS_MANIFEST_SCHEMA_VERSION,
                robustness_id=robustness_id,
                test_type=job.test_type,
                base_experiment_id=job.base_experiment_id,
                base_run_id=entry.run_id,
                dataset_catalog_id=job.dataset_catalog_id,
                config=config,
                created_at=_utc_now(),
                children=tuple(children),
                bootstrap_result=bootstrap_result,
                summary=summary,
            )
            save_robustness_manifest(self.root, manifest)

            def _finish(job_: RobustnessJob) -> None:
                job_.status = "completed"
                job_.updated_at = _utc_now()
                job_.finished_at = job_.updated_at
                if n_failed:
                    job_.error = f"{n_failed} von {len(children)} Kind-Läufen fehlgeschlagen"
                    job_.error_detail = json.dumps(
                        [c.to_dict() for c in children if c.status != "complete"]
                    )
                else:
                    job_.error = None
                    job_.error_detail = None

            _finish_owned(_finish)
        except Exception as exc:  # noqa: BLE001 — persist structured failure
            err_msg = str(exc)
            err_detail = repr(exc)

            def _fail(job_: RobustnessJob) -> None:
                job_.status = "failed"
                job_.finished_at = _utc_now()
                job_.updated_at = job_.finished_at
                job_.error = err_msg
                job_.error_detail = err_detail

            _finish_owned(_fail)
        finally:
            stop_heartbeat.set()
            heartbeat_thread.join(timeout=2)
            self.store.clear_thread(robustness_id)
