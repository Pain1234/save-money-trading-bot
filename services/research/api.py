"""Research FastAPI routes — read + minimal write (Issues #240 / #242)."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query

from research.gate_service import GateService
from research.robustness_service import RobustnessOrchestrationService
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


def get_robustness_service() -> RobustnessOrchestrationService:
    return RobustnessOrchestrationService(research_root_from_env())


def get_gate_service() -> GateService:
    return GateService(research_root_from_env())


ResearchSvc = Annotated[ResearchReadService, Depends(get_research_service)]
ResearchWriteSvc = Annotated[ResearchWriteService, Depends(get_research_write_service)]
RobustnessSvc = Annotated[
    RobustnessOrchestrationService, Depends(get_robustness_service)
]
GateSvc = Annotated[GateService, Depends(get_gate_service)]


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
        # May exist only as a pending job (created / running, not yet in registry).
        try:
            status = write_svc.get_status(experiment_id)
        except (KeyError, ValueError):
            raise HTTPException(status_code=404, detail="experiment not found") from None
        return {
            "summary": {
                "experiment_id": experiment_id,
                "run_id": status.get("run_id"),
                "status": status["status"],
                "strategy_version": None,
                "strategy_id": None,
                "dataset_version": None,
                "cost_model_version": None,
                "benchmark_ref": None,
                "created_at": status["job"].get("created_at"),
                "symbols": [],
                "time_range_start": None,
                "time_range_end": None,
                "timeframe": None,
                "git_commit": None,
                "duration_seconds": status.get("elapsed_seconds"),
                "net_pnl": None,
                "max_drawdown": None,
                "closed_trades": None,
                "hit_rate": None,
                "profit_factor": None,
                "integrity_ok": True,
                "integrity_error": None,
            },
            "metadata": {
                "experiment_id": experiment_id,
                "run_id": status.get("run_id"),
                "status": status["status"],
                "strategy_version": None,
                "git_commit": None,
                "dataset_version": None,
                "seed": None,
                "created_at": status["job"].get("created_at"),
                "started_at": status.get("started_at"),
                "finalized_at": status.get("finished_at"),
                "duration_seconds": status.get("elapsed_seconds"),
            },
            "config": {},
            "metrics": {},
            "equity": [],
            "drawdown": [],
            "artifacts": {},
            "integrity": {"ok": True, "error": None},
            "job": status,
        }
    except PermissionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    try:
        detail["job"] = write_svc.get_status(experiment_id)
    except (KeyError, ValueError):
        detail["job"] = None
    return detail


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


@router.get("/robustness")
def research_list_robustness_jobs(
    svc: RobustnessSvc,
    base_experiment_id: Annotated[str | None, Query()] = None,
) -> dict[str, Any]:
    items = svc.list_jobs(base_experiment_id=base_experiment_id)
    return {"items": items, "count": len(items)}


@router.post("/robustness")
def research_create_robustness_job(
    payload: dict[str, Any],
    svc: RobustnessSvc,
) -> dict[str, Any]:
    try:
        return svc.create(payload)
    except ResearchWriteError as exc:
        raise HTTPException(
            status_code=422,
            detail={"message": str(exc), "fields": exc.field_errors},
        ) from exc


@router.post("/robustness/{robustness_id}/start")
def research_start_robustness_job(
    robustness_id: str,
    svc: RobustnessSvc,
) -> dict[str, Any]:
    try:
        return svc.start(robustness_id)
    except KeyError:
        raise HTTPException(
            status_code=404, detail="robustness job not found"
        ) from None
    except ResearchWriteError as exc:
        raise HTTPException(
            status_code=409,
            detail={"message": str(exc), "fields": exc.field_errors},
        ) from exc


@router.get("/robustness/{robustness_id}/status")
def research_robustness_status(
    robustness_id: str,
    svc: RobustnessSvc,
) -> dict[str, Any]:
    try:
        return svc.get_status(robustness_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except KeyError:
        raise HTTPException(
            status_code=404, detail="robustness job not found"
        ) from None


@router.get("/robustness/{robustness_id}")
def research_robustness_detail(
    robustness_id: str,
    svc: RobustnessSvc,
) -> dict[str, Any]:
    try:
        status = svc.get_status(robustness_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except KeyError:
        raise HTTPException(
            status_code=404, detail="robustness job not found"
        ) from None
    manifest = svc.get_manifest(robustness_id)
    return {**status, "manifest": manifest}


@router.get("/gate-policies")
def research_list_gate_policies(svc: GateSvc) -> dict[str, Any]:
    """Registered gate policy versions + content hash (read-only, no secrets)."""
    items = svc.list_policies()
    return {"items": items, "count": len(items)}


@router.get("/gates")
def research_list_gates(
    svc: GateSvc,
    run_id: Annotated[str | None, Query()] = None,
) -> dict[str, Any]:
    items = svc.list_all(run_id=run_id)
    return {"items": items, "count": len(items)}


@router.post("/gates/evaluate")
def research_evaluate_gate(
    payload: dict[str, Any],
    svc: GateSvc,
) -> dict[str, Any]:
    """Evaluate a versioned gate policy against an already-completed run.

    Read-only over existing artifacts; append-only persistence; no
    live/paper promotion (P4.7c / #248).
    """
    try:
        return svc.evaluate(payload)
    except ResearchWriteError as exc:
        raise HTTPException(
            status_code=422,
            detail={"message": str(exc), "fields": exc.field_errors},
        ) from exc


@router.get("/gates/{gate_run_id}")
def research_gate_detail(
    gate_run_id: str,
    svc: GateSvc,
) -> dict[str, Any]:
    try:
        return svc.get(gate_run_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except KeyError:
        raise HTTPException(status_code=404, detail="gate result not found") from None


@router.post("/gates/{gate_run_id}/invalidate")
def research_invalidate_gate(
    gate_run_id: str,
    payload: dict[str, Any],
    svc: GateSvc,
) -> dict[str, Any]:
    """Append-only invalidation (never mutates the original gate record)."""
    try:
        return svc.invalidate(gate_run_id, payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except KeyError:
        raise HTTPException(status_code=404, detail="gate result not found") from None
    except ResearchWriteError as exc:
        raise HTTPException(
            status_code=409,
            detail={"message": str(exc), "fields": exc.field_errors},
        ) from exc


def is_research_write_path(path: str) -> bool:
    """POST allow-list for private research write surface on the dashboard API."""
    if path.rstrip("/") == "/api/v1/research/experiments":
        return True
    if path.startswith("/api/v1/research/experiments/") and path.endswith("/start"):
        return True
    if path.rstrip("/") == "/api/v1/research/robustness":
        return True
    if path.startswith("/api/v1/research/robustness/") and path.endswith("/start"):
        return True
    if path.rstrip("/") == "/api/v1/research/gates/evaluate":
        return True
    if path.startswith("/api/v1/research/gates/") and path.endswith("/invalidate"):
        return True
    return False
