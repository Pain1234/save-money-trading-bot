"""Research FastAPI routes — read + minimal write (Issues #240 / #242)."""

from __future__ import annotations

import json
from typing import Annotated, Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query

from research.service import ResearchReadService, research_root_from_env
from research.write_service import (
    ResearchWriteError,
    ResearchWriteService,
    list_strategies,
    load_dataset_catalog,
    strategy_detail,
    strategy_schema,
)

router = APIRouter(prefix="/api/v1/research", tags=["research"])


def get_research_service() -> ResearchReadService:
    return ResearchReadService(research_root_from_env())


def get_research_write_service() -> ResearchWriteService:
    return ResearchWriteService(research_root_from_env())


ResearchSvc = Annotated[ResearchReadService, Depends(get_research_service)]
ResearchWriteSvc = Annotated[ResearchWriteService, Depends(get_research_write_service)]


@router.get("/overview")
def research_overview(svc: ResearchSvc) -> dict[str, Any]:
    return svc.overview()


@router.get("/experiments")
def research_experiments(
    svc: ResearchSvc,
    status: Annotated[str | None, Query()] = None,
    strategy_version: Annotated[str | None, Query()] = None,
    q: Annotated[str | None, Query()] = None,
) -> dict[str, Any]:
    items = svc.list_experiments(
        status=status,
        strategy_version=strategy_version,
        q=q,
    )
    return {"items": items, "count": len(items)}


@router.get("/experiments/{experiment_id}")
def research_experiment_detail(
    experiment_id: str,
    svc: ResearchSvc,
    write_svc: ResearchWriteSvc,
) -> dict[str, Any]:
    try:
        detail = svc.experiment_detail(experiment_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except KeyError:
        # May exist only as a pending/failed job (not yet in registry).
        try:
            status = write_svc.get_status(experiment_id)
        except (KeyError, ValueError):
            raise HTTPException(status_code=404, detail="experiment not found") from None
        detail = _detail_from_job_only(experiment_id, status, write_svc)
    except PermissionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    else:
        try:
            detail["job"] = write_svc.get_status(experiment_id)
        except (KeyError, ValueError):
            detail["job"] = None
    return detail


def _detail_from_job_only(
    experiment_id: str,
    status: dict[str, Any],
    write_svc: ResearchWriteSvc,
) -> dict[str, Any]:
    """Build a Lab-safe detail payload when registry has no complete run yet."""
    job_status = str(status.get("status") or "")
    job_error = status.get("error")
    spec: dict[str, Any] = {}
    try:
        pending = write_svc.store.pending_spec_path(experiment_id)
        if pending.is_file():
            raw = json.loads(pending.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                spec = raw
    except (OSError, json.JSONDecodeError, TypeError):
        spec = {}

    symbols = [str(s) for s in (spec.get("symbols") or [])]
    tr = spec.get("time_range") if isinstance(spec.get("time_range"), dict) else {}
    params = spec.get("parameters") if isinstance(spec.get("parameters"), dict) else {}
    failed = job_status == "failed"

    return {
        "summary": {
            "experiment_id": experiment_id,
            "run_id": status.get("run_id"),
            "status": job_status,
            "strategy_version": spec.get("strategy_version"),
            "strategy_id": (params or {}).get("strategy_id"),
            "dataset_version": (spec.get("dataset_manifest_ref") or {}).get("dataset_id"),
            "cost_model_version": None,
            "benchmark_ref": spec.get("benchmark"),
            "created_at": status.get("job", {}).get("created_at")
            if isinstance(status.get("job"), dict)
            else status.get("started_at"),
            "symbols": symbols,
            "time_range_start": tr.get("start"),
            "time_range_end": tr.get("end"),
            "timeframe": None,
            "git_commit": None,
            "duration_seconds": status.get("elapsed_seconds"),
            "net_pnl": None,
            "max_drawdown": None,
            "closed_trades": None,
            "hit_rate": None,
            "profit_factor": None,
            "integrity_ok": not failed,
            "integrity_error": str(job_error) if failed and job_error else None,
        },
        "metadata": {
            "experiment_id": experiment_id,
            "run_id": status.get("run_id"),
            "status": job_status,
            "strategy_version": spec.get("strategy_version"),
            "git_commit": None,
            "dataset_version": (spec.get("dataset_manifest_ref") or {}).get("dataset_id"),
            "seed": spec.get("random_seed"),
            "created_at": (
                status.get("job", {}).get("created_at")
                if isinstance(status.get("job"), dict)
                else None
            ),
            "started_at": status.get("started_at"),
            "finalized_at": status.get("finished_at"),
            "duration_seconds": status.get("elapsed_seconds"),
        },
        "config": {
            "symbols": symbols,
            "time_range_start": tr.get("start"),
            "time_range_end": tr.get("end"),
            "timeframe": "1D",
            "starting_capital": (
                str(spec["starting_capital"]) if spec.get("starting_capital") is not None else None
            ),
            "parameters": params,
            "fee_assumption": spec.get("fee_assumption"),
            "slippage_assumption": spec.get("slippage_assumption"),
            "funding_assumption": spec.get("funding_assumption"),
            "costs": None,
            "in_sample_config": "Nicht verfügbar",
            "out_of_sample_config": "Nicht verfügbar",
            "benchmark": str(spec.get("benchmark") or "Nicht verfügbar"),
            "hypothesis": spec.get("hypothesis"),
        },
        "metrics": {},
        "equity": [],
        "drawdown": [],
        "artifacts": {
            "has_experiment_spec": bool(spec),
            "has_run_manifest": False,
            "has_metrics": False,
            "has_equity": False,
            "has_costs": False,
            "has_trades": False,
            "has_chart_data": False,
        },
        "integrity": {
            "ok": not failed,
            "error": str(job_error) if failed and job_error else None,
        },
        "job": status,
    }


@router.get("/experiments/{experiment_id}/metrics")
def research_experiment_metrics(
    experiment_id: str,
    svc: ResearchSvc,
    write_svc: ResearchWriteSvc,
) -> dict[str, Any]:
    detail = research_experiment_detail(experiment_id, svc, write_svc)
    return {"experiment_id": experiment_id, "metrics": detail.get("metrics", {})}


@router.get("/experiments/{experiment_id}/equity")
def research_experiment_equity(
    experiment_id: str,
    svc: ResearchSvc,
    write_svc: ResearchWriteSvc,
) -> dict[str, Any]:
    detail = research_experiment_detail(experiment_id, svc, write_svc)
    return {
        "experiment_id": experiment_id,
        "equity": detail.get("equity", []),
        "drawdown": detail.get("drawdown", []),
    }


@router.get("/experiments/{experiment_id}/trades")
def research_experiment_trades(
    experiment_id: str,
    svc: ResearchSvc,
    symbol: Annotated[str | None, Query()] = None,
) -> dict[str, Any]:
    try:
        return svc.experiment_trades(experiment_id, symbol=symbol)
    except KeyError:
        raise HTTPException(status_code=404, detail="experiment not found") from None
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/experiments/{experiment_id}/chart-data")
def research_experiment_chart_data(
    experiment_id: str,
    svc: ResearchSvc,
    symbol: Annotated[str, Query()],
) -> dict[str, Any]:
    try:
        return svc.experiment_chart_data(experiment_id, symbol=symbol)
    except KeyError:
        raise HTTPException(status_code=404, detail="experiment not found") from None
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/experiments/{experiment_id}/artifacts")
def research_experiment_artifacts(
    experiment_id: str,
    svc: ResearchSvc,
    write_svc: ResearchWriteSvc,
) -> dict[str, Any]:
    detail = research_experiment_detail(experiment_id, svc, write_svc)
    return {"experiment_id": experiment_id, "artifacts": detail.get("artifacts", {})}


@router.get("/strategies")
def research_strategies(svc: ResearchSvc) -> dict[str, Any]:
    experiments = svc.list_experiments()
    items = []
    for base in list_strategies():
        detail = strategy_detail(
            str(base["strategy_id"]),
            experiments=experiments,
        )
        items.append(
            {
                **base,
                "experiment_count": detail["experiment_count"],
                "last_run": detail["last_run"],
            }
        )
    return {"items": items}


@router.get("/strategies/{strategy_id}")
def research_strategy_detail(strategy_id: str, svc: ResearchSvc) -> dict[str, Any]:
    try:
        return strategy_detail(
            strategy_id,
            experiments=svc.list_experiments(),
        )
    except ResearchWriteError as exc:
        raise HTTPException(
            status_code=404,
            detail={"message": str(exc), "fields": exc.field_errors},
        ) from exc


@router.get("/strategies/{strategy_id}/schema")
def research_strategy_schema(strategy_id: str) -> dict[str, Any]:
    try:
        return strategy_schema(strategy_id)
    except ResearchWriteError as exc:
        raise HTTPException(
            status_code=404,
            detail={"message": str(exc), "fields": exc.field_errors},
        ) from exc


@router.get("/datasets")
def research_datasets() -> dict[str, Any]:
    items = [
        {
            "id": e.id,
            "label": e.label,
            "dataset_id": e.dataset_id,
            "symbols": list(e.symbols),
        }
        for e in load_dataset_catalog()
    ]
    return {"items": items, "count": len(items)}


@router.post("/experiments")
def research_create_experiment(
    payload: dict[str, Any],
    write_svc: ResearchWriteSvc,
) -> dict[str, Any]:
    try:
        return write_svc.create_experiment(payload)
    except ResearchWriteError as exc:
        raise HTTPException(
            status_code=422,
            detail={"message": str(exc), "fields": exc.field_errors},
        ) from exc


@router.post("/experiments/{experiment_id}/start")
def research_start_experiment(
    experiment_id: str,
    write_svc: ResearchWriteSvc,
    background_tasks: BackgroundTasks,
) -> dict[str, Any]:
    # BackgroundTasks kept for FastAPI symmetry; execution is threaded inside start.
    _ = background_tasks
    try:
        return write_svc.start_experiment(experiment_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="experiment not found") from None
    except ResearchWriteError as exc:
        raise HTTPException(
            status_code=409,
            detail={"message": str(exc), "fields": exc.field_errors},
        ) from exc


@router.get("/experiments/{experiment_id}/status")
def research_experiment_status(
    experiment_id: str,
    write_svc: ResearchWriteSvc,
) -> dict[str, Any]:
    try:
        return write_svc.get_status(experiment_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except KeyError:
        raise HTTPException(status_code=404, detail="experiment not found") from None


def is_research_write_path(path: str) -> bool:
    """POST allow-list for private research write surface on the dashboard API."""
    if path.rstrip("/") == "/api/v1/research/experiments":
        return True
    if path.startswith("/api/v1/research/experiments/") and path.endswith("/start"):
        return True
    return False
