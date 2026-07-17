"""Create/start research experiments via existing run_experiment (Issue #242)."""

from __future__ import annotations

import json
import os
import re
import threading
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any

from backtester.models import HistoricalDataBundle
from pydantic import ValidationError
from strategy_engine.constants import STRATEGY_VERSION
from strategy_engine.models import StrategyParameters, Timeframe

from research.artifacts import load_checksums
from research.experiment_spec import (
    ALLOWED_SYMBOLS,
    ExperimentSpec,
    parse_experiment_spec,
    save_experiment_spec,
)
from research.identity import compute_experiment_id
from research.jobs import ResearchJob, ResearchJobStore, _utc_now
from research.registry import ExperimentRegistry
from research.runner import RunRequest, run_experiment
from research.strategy_resolver import known_strategy_ids
from research.validation import assert_no_secrets

_SAFE_CATALOG_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
_FIELD_ERROR = dict[str, str]


@dataclass(frozen=True)
class DatasetCatalogEntry:
    id: str
    label: str
    dataset_id: str
    content_hash: str
    manifest_path: str
    bundle_path: str
    symbols: tuple[str, ...]


class ResearchWriteError(Exception):
    def __init__(self, message: str, *, field_errors: dict[str, str] | None = None) -> None:
        super().__init__(message)
        self.field_errors = field_errors or {}


def repo_root_from_env() -> Path:
    raw = os.environ.get("RESEARCH_REPO_ROOT", "").strip()
    if raw:
        return Path(raw).resolve()
    # services/research/write_service.py → repo root
    return Path(__file__).resolve().parents[2]


def default_local_catalog_path(*, repo_root: Path | None = None) -> Path:
    """Dev checkout fallback: committed local-lab catalog (Issue #264)."""
    root = (repo_root or repo_root_from_env()).resolve()
    return root / "examples" / "research" / "local_lab" / "catalog.json"


def load_dataset_catalog() -> list[DatasetCatalogEntry]:
    """Load allowed datasets (no free-form client paths).

    Resolution order:
    1. ``RESEARCH_DATASET_CATALOG_PATH``
    2. ``RESEARCH_DATASET_CATALOG_JSON``
    3. ``examples/research/local_lab/catalog.json`` under ``RESEARCH_REPO_ROOT``
       (local/dev convenience; empty if the file is missing)
    """
    path_raw = os.environ.get("RESEARCH_DATASET_CATALOG_PATH", "").strip()
    json_raw = os.environ.get("RESEARCH_DATASET_CATALOG_JSON", "").strip()
    payload: list[Any]
    if path_raw:
        data = json.loads(Path(path_raw).read_text(encoding="utf-8"))
        payload = data if isinstance(data, list) else data.get("datasets", [])
    elif json_raw:
        data = json.loads(json_raw)
        payload = data if isinstance(data, list) else data.get("datasets", [])
    else:
        fallback = default_local_catalog_path()
        if not fallback.is_file():
            return []
        data = json.loads(fallback.read_text(encoding="utf-8"))
        payload = data if isinstance(data, list) else data.get("datasets", [])

    entries: list[DatasetCatalogEntry] = []
    for row in payload:
        if not isinstance(row, dict):
            continue
        catalog_id = str(row["id"])
        if not _SAFE_CATALOG_ID.fullmatch(catalog_id):
            continue
        symbols = tuple(str(s) for s in (row.get("symbols") or []))
        entries.append(
            DatasetCatalogEntry(
                id=catalog_id,
                label=str(row.get("label") or catalog_id),
                dataset_id=str(row["dataset_id"]),
                content_hash=str(row["content_hash"]),
                manifest_path=str(row["manifest_path"]),
                bundle_path=str(row["bundle_path"]),
                symbols=symbols,
            )
        )
    return entries


def list_strategies() -> list[dict[str, Any]]:
    return [
        {
            "strategy_id": sid,
            "strategy_version": STRATEGY_VERSION,
            "label": sid,
            "timeframes": [t.value for t in Timeframe],
            "timeframe_note": "Trend V1 requires multi-timeframe candles (1D/1W/1M).",
            "symbols": sorted(ALLOWED_SYMBOLS),
        }
        for sid in known_strategy_ids()
    ]


def strategy_schema(strategy_id: str) -> dict[str, Any]:
    if strategy_id not in known_strategy_ids():
        raise ResearchWriteError(
            f"unknown strategy_id {strategy_id!r}",
            field_errors={"strategy_id": "Strategie ist nicht registriert"},
        )
    params_schema = StrategyParameters.model_json_schema()
    defaults = StrategyParameters().model_dump(mode="json")
    return {
        "strategy_id": strategy_id,
        "strategy_version": STRATEGY_VERSION,
        "parameters_schema": params_schema,
        "parameter_defaults": defaults,
        "symbols": sorted(ALLOWED_SYMBOLS),
        "timeframes": [t.value for t in Timeframe],
        "fee_fields": ["entry_fee_rate", "exit_fee_rate"],
        "slippage_fields": ["slippage_bps"],
    }


def _field_errors_from_validation(exc: ValidationError) -> dict[str, str]:
    out: dict[str, str] = {}
    for err in exc.errors():
        loc = ".".join(str(p) for p in err.get("loc", ()) if p != "body")
        out[loc or "payload"] = err.get("msg", "invalid")
    return out


def build_spec_from_payload(payload: dict[str, Any]) -> ExperimentSpec:
    """Validate Lab payload and build a canonical ExperimentSpec."""
    assert_no_secrets(payload)
    field_errors: dict[str, str] = {}

    strategy_id = str(payload.get("strategy_id") or "").strip()
    if strategy_id not in known_strategy_ids():
        field_errors["strategy_id"] = "Strategie ist nicht registriert"

    strategy_version = str(payload.get("strategy_version") or STRATEGY_VERSION)
    if strategy_version != STRATEGY_VERSION:
        field_errors["strategy_version"] = (
            f"Nicht unterstützte Strategieversion {strategy_version!r}; "
            f"erwartet {STRATEGY_VERSION!r}"
        )

    catalog_id = str(payload.get("dataset_catalog_id") or "").strip()
    catalog = {e.id: e for e in load_dataset_catalog()}
    if not catalog_id or catalog_id not in catalog:
        field_errors["dataset_catalog_id"] = (
            "Dataset-Katalog-Eintrag fehlt oder ist unbekannt "
            "(kein freier Dateipfad erlaubt)"
        )
        entry = None
    else:
        entry = catalog[catalog_id]

    symbols_raw = payload.get("symbols") or []
    if not isinstance(symbols_raw, list) or not symbols_raw:
        field_errors["symbols"] = "Mindestens ein Symbol erforderlich"
    else:
        for sym in symbols_raw:
            if str(sym) not in ALLOWED_SYMBOLS:
                field_errors["symbols"] = f"Symbol {sym!r} ist nicht unterstützt"

    timeframe = str(payload.get("timeframe") or Timeframe.DAILY.value)
    if timeframe not in {t.value for t in Timeframe}:
        field_errors["timeframe"] = f"Timeframe {timeframe!r} ist ungültig"

    name = str(payload.get("name") or payload.get("hypothesis") or "").strip()
    if not name:
        field_errors["name"] = "Experimentname / Hypothese ist erforderlich"

    tr = payload.get("time_range") or {}
    if not isinstance(tr, dict) or not tr.get("start") or not tr.get("end"):
        field_errors["time_range"] = "Start- und Enddatum sind erforderlich"

    try:
        capital = Decimal(str(payload.get("starting_capital", "0")))
        if capital <= 0:
            field_errors["starting_capital"] = "Startkapital muss positiv sein"
    except Exception:  # noqa: BLE001
        field_errors["starting_capital"] = "Startkapital ist ungültig"
        capital = Decimal("0")

    fee = payload.get("fee_assumption") or {}
    slip = payload.get("slippage_assumption") or {}
    try:
        entry_fee = Decimal(str(fee.get("entry_fee_rate", "0")))
        exit_fee = Decimal(str(fee.get("exit_fee_rate", "0")))
        if entry_fee < 0 or exit_fee < 0:
            field_errors["fee_assumption"] = "Gebühren dürfen nicht negativ sein"
    except Exception:  # noqa: BLE001
        field_errors["fee_assumption"] = "Gebührenparameter ungültig"
        entry_fee = Decimal("0")
        exit_fee = Decimal("0")
    try:
        slippage_bps = Decimal(str(slip.get("slippage_bps", "0")))
        if slippage_bps < 0:
            field_errors["slippage_assumption"] = "Slippage darf nicht negativ sein"
    except Exception:  # noqa: BLE001
        field_errors["slippage_assumption"] = "Slippage-Parameter ungültig"
        slippage_bps = Decimal("0")

    raw_params = dict(payload.get("parameters") or {})
    raw_params["strategy_id"] = strategy_id
    raw_params["strategy_version"] = strategy_version
    try:
        # Validate against StrategyParameters (unknown keys fail).
        params_for_engine = {k: v for k, v in raw_params.items() if k != "strategy_id"}
        StrategyParameters.model_validate(params_for_engine)
    except ValidationError as exc:
        for loc, msg in _field_errors_from_validation(exc).items():
            field_errors[f"parameters.{loc}"] = msg

    if field_errors:
        raise ResearchWriteError("Validierung fehlgeschlagen", field_errors=field_errors)

    assert entry is not None
    if entry.symbols:
        for sym in symbols_raw:
            if str(sym) not in entry.symbols:
                raise ResearchWriteError(
                    "Symbol nicht im gewählten Dataset",
                    field_errors={
                        "symbols": f"{sym!r} ist in Dataset {entry.id!r} nicht enthalten"
                    },
                )

    notes = str(payload.get("notes") or "")
    seed = payload.get("random_seed")
    random_seed = int(seed) if seed is not None and str(seed) != "" else None

    spec_payload: dict[str, Any] = {
        "schema_version": "1.0",
        "hypothesis": name,
        "strategy_version": strategy_version,
        "parameters": {
            k: v
            for k, v in raw_params.items()
            if k not in {"strategy_version"}
        },
        "dataset_manifest_ref": {
            "dataset_id": entry.dataset_id,
            "content_hash": entry.content_hash,
            "manifest_path": entry.manifest_path,
        },
        "symbols": [str(s) for s in symbols_raw],
        "time_range": {
            "start": tr["start"],
            "end": tr["end"],
        },
        "starting_capital": str(capital),
        "fee_assumption": {
            "entry_fee_rate": str(entry_fee),
            "exit_fee_rate": str(exit_fee),
            "model_version": str(fee.get("model_version") or "1.0"),
        },
        "slippage_assumption": {
            "slippage_bps": str(slippage_bps),
            "model_version": str(slip.get("model_version") or "1.0"),
        },
        "funding_assumption": {
            "enabled": bool((payload.get("funding_assumption") or {}).get("enabled", False)),
            "assumed_rate": (payload.get("funding_assumption") or {}).get("assumed_rate"),
            "model_version": "1.0",
        },
        "benchmark": str(
            payload.get("benchmark") or f"buy_and_hold_{symbols_raw[0]}"
        ),
        "random_seed": random_seed,
        "notes": notes,
        "owner": str(payload.get("owner") or "dashboard"),
    }

    try:
        return parse_experiment_spec(spec_payload)
    except (ValidationError, ValueError, TypeError) as exc:
        if isinstance(exc, ValidationError):
            raise ResearchWriteError(
                "ExperimentSpec ungültig",
                field_errors=_field_errors_from_validation(exc),
            ) from exc
        raise ResearchWriteError(
            str(exc),
            field_errors={"spec": str(exc)},
        ) from exc


class ResearchWriteService:
    def __init__(
        self,
        root: Path,
        *,
        repo_root: Path | None = None,
        allow_dirty_git: bool | None = None,
    ) -> None:
        self.root = root.resolve()
        self.repo_root = (repo_root or repo_root_from_env()).resolve()
        self.store = ResearchJobStore(self.root)
        self.registry = ExperimentRegistry(self.root)
        if allow_dirty_git is None:
            allow_dirty_git = os.environ.get("RESEARCH_ALLOW_DIRTY_GIT", "").strip() in {
                "1",
                "true",
                "TRUE",
                "yes",
            }
        self.allow_dirty_git = bool(allow_dirty_git)

    def create_experiment(self, payload: dict[str, Any]) -> dict[str, Any]:
        from research.jobs import TerminalStatus

        spec = build_spec_from_payload(payload)
        experiment_id = compute_experiment_id(spec)
        pending = self.store.pending_spec_path(experiment_id)

        with self.store.lock_for(experiment_id):
            existing = self.store.get(experiment_id)
            if existing is not None:
                existing = self.store.mark_stale_if_needed(existing)
                if existing.status in {"queued", "running"}:
                    raise ResearchWriteError(
                        "Experiment läuft bereits",
                        field_errors={"experiment_id": "Doppelstart verhindert"},
                    )
                if existing.status in TerminalStatus:
                    # Idempotent: do not reset terminal jobs (no implicit Re-run).
                    return {
                        "experiment_id": experiment_id,
                        "status": existing.status,
                        "job": existing.to_dict(),
                        "spec_path": str(pending),
                        "already_exists": True,
                    }

            pending.parent.mkdir(parents=True, exist_ok=True)
            save_experiment_spec(spec, pending)

            now = _utc_now()
            job = ResearchJob(
                experiment_id=experiment_id,
                status="created",
                created_at=existing.created_at if existing else now,
                updated_at=now,
                dataset_catalog_id=str(payload.get("dataset_catalog_id") or ""),
                name=spec.hypothesis,
            )
            self.store.save(job)
            return {
                "experiment_id": experiment_id,
                "status": job.status,
                "job": job.to_dict(),
                "spec_path": str(pending),
                "already_exists": False,
            }

    def start_experiment(self, experiment_id: str) -> dict[str, Any]:
        from research.jobs import JobTransitionError
        from research.service import assert_safe_id

        experiment_id = assert_safe_id(experiment_id, field="experiment_id")

        # Resolve catalog outside the transition lock (I/O), then CAS created→queued.
        job_probe = self.store.get(experiment_id)
        if job_probe is None:
            raise KeyError(experiment_id)
        job_probe = self.store.mark_stale_if_needed(job_probe)

        pending = self.store.pending_spec_path(experiment_id)
        if not pending.is_file():
            raise ResearchWriteError(
                "Gespeicherte Experiment-Konfiguration fehlt",
                field_errors={"spec": "pending experiment.json nicht gefunden"},
            )

        catalog_id = job_probe.dataset_catalog_id or ""
        catalog = {e.id: e for e in load_dataset_catalog()}
        if catalog_id not in catalog:
            raise ResearchWriteError(
                "Dataset-Katalog-Eintrag fehlt",
                field_errors={"dataset_catalog_id": "unbekannt"},
            )
        entry = catalog[catalog_id]

        def _to_queued(job: ResearchJob) -> None:
            job.status = "queued"
            job.updated_at = _utc_now()
            job.error = None
            job.error_detail = None
            job.finished_at = None
            job.started_at = None

        try:
            job = self.store.compare_and_set(
                experiment_id,
                expected_status="created",
                mutate=_to_queued,
            )
        except JobTransitionError as exc:
            current = exc.current_status
            if current in {"queued", "running"}:
                raise ResearchWriteError(
                    "Experiment läuft bereits oder ist in der Warteschlange",
                    field_errors={"status": "Doppelstart verhindert"},
                ) from exc
            raise ResearchWriteError(
                "Nur Experimente im Status created können gestartet werden "
                "(kein Re-run in V1)",
                field_errors={"status": f"Aktueller Status: {current}"},
            ) from exc

        thread = threading.Thread(
            target=self._run_job,
            args=(experiment_id, entry),
            name=f"research-job-{experiment_id[:16]}",
            daemon=True,
        )
        self.store.register_thread(experiment_id, thread)
        thread.start()

        refreshed = self.store.get(experiment_id)
        return {
            "experiment_id": experiment_id,
            "status": "queued",
            "job": (refreshed or job).to_dict(),
        }

    def get_status(self, experiment_id: str) -> dict[str, Any]:
        from research.service import assert_safe_id

        experiment_id = assert_safe_id(experiment_id, field="experiment_id")
        job = self.store.get(experiment_id)
        if job is None:
            raise KeyError(experiment_id)
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
            "experiment_id": experiment_id,
            "status": job.status,
            "started_at": job.started_at,
            "finished_at": job.finished_at,
            "elapsed_seconds": elapsed,
            "run_id": job.run_id,
            "error": job.error,
            "error_detail": job.error_detail,
            "job": job.to_dict(),
            "worker_alive": self.store.is_active(experiment_id),
        }

    def _run_job(self, experiment_id: str, entry: DatasetCatalogEntry) -> None:
        from research.jobs import JobTransitionError

        try:
            def _to_running(job: ResearchJob) -> None:
                job.status = "running"
                job.started_at = _utc_now()
                job.updated_at = job.started_at

            try:
                self.store.compare_and_set(
                    experiment_id,
                    expected_status="queued",
                    mutate=_to_running,
                )
            except JobTransitionError:
                return

            spec = parse_experiment_spec(
                json.loads(
                    self.store.pending_spec_path(experiment_id).read_text(encoding="utf-8")
                )
            )
            bundle_path = Path(entry.bundle_path)
            if not bundle_path.is_absolute():
                bundle_path = (self.repo_root / bundle_path).resolve()
            # Bundle must stay under repo or research root (no arbitrary FS).
            try:
                bundle_path.relative_to(self.repo_root)
            except ValueError:
                try:
                    bundle_path.relative_to(self.root)
                except ValueError as exc:
                    msg = "bundle path escapes allowed roots"
                    raise PermissionError(msg) from exc

            bundle = HistoricalDataBundle.model_validate(
                json.loads(bundle_path.read_text(encoding="utf-8"))
            )
            outcome = run_experiment(
                RunRequest(
                    spec=spec,
                    bundle=bundle,
                    artifacts_root=self.root,
                    repo_root=self.repo_root,
                    allow_dirty_git=self.allow_dirty_git,
                )
            )

            def _finish(job: ResearchJob) -> None:
                job.run_id = outcome.run_id
                job.attempt_id = outcome.attempt_id
                job.updated_at = _utc_now()
                job.finished_at = job.updated_at
                if outcome.status == "complete" and outcome.artifact_path is not None:
                    costs_path = outcome.artifact_path / "costs.json"
                    cost_ver = "1.0"
                    if costs_path.is_file():
                        costs = json.loads(costs_path.read_text(encoding="utf-8"))
                        cost_ver = str(costs.get("cost_model_version", "1.0"))
                    self.registry.register_complete(
                        experiment_id=outcome.experiment_id,
                        run_id=outcome.run_id,
                        attempt_id=outcome.attempt_id,
                        strategy_version=spec.strategy_version,
                        dataset_version=spec.dataset_manifest_ref.dataset_id,
                        cost_model_version=cost_ver,
                        benchmark_ref=spec.benchmark,
                        artifact_path=outcome.artifact_path,
                        checksums=load_checksums(outcome.artifact_path),
                    )
                    job.status = "completed"
                    job.error = None
                    job.error_detail = None
                else:
                    job.status = "failed"
                    job.error = outcome.error or f"Run status: {outcome.status}"
                    job.error_detail = outcome.error

            self.store.update(experiment_id, _finish)
        except Exception as exc:  # noqa: BLE001 — persist structured failure
            err_msg = str(exc)
            err_detail = repr(exc)

            def _fail(job: ResearchJob) -> None:
                job.status = "failed"
                job.finished_at = _utc_now()
                job.updated_at = job.finished_at
                job.error = err_msg
                job.error_detail = err_detail

            try:
                self.store.update(experiment_id, _fail)
            except KeyError:
                pass
        finally:
            self.store.clear_thread(experiment_id)
