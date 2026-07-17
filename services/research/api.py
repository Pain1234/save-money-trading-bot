"""Read-only Research FastAPI routes over ExperimentRegistry (Issue #240)."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query

from research.service import ResearchReadService, research_root_from_env

router = APIRouter(prefix="/api/v1/research", tags=["research"])


def get_research_service() -> ResearchReadService:
    return ResearchReadService(research_root_from_env())


ResearchSvc = Annotated[ResearchReadService, Depends(get_research_service)]


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
) -> dict[str, Any]:
    try:
        return svc.experiment_detail(experiment_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except KeyError:
        raise HTTPException(status_code=404, detail="experiment not found") from None
    except PermissionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/experiments/{experiment_id}/metrics")
def research_experiment_metrics(
    experiment_id: str,
    svc: ResearchSvc,
) -> dict[str, Any]:
    detail = research_experiment_detail(experiment_id, svc)
    return {"experiment_id": experiment_id, "metrics": detail["metrics"]}


@router.get("/experiments/{experiment_id}/equity")
def research_experiment_equity(
    experiment_id: str,
    svc: ResearchSvc,
) -> dict[str, Any]:
    detail = research_experiment_detail(experiment_id, svc)
    return {
        "experiment_id": experiment_id,
        "equity": detail["equity"],
        "drawdown": detail["drawdown"],
    }


@router.get("/experiments/{experiment_id}/artifacts")
def research_experiment_artifacts(
    experiment_id: str,
    svc: ResearchSvc,
) -> dict[str, Any]:
    detail = research_experiment_detail(experiment_id, svc)
    return {"experiment_id": experiment_id, "artifacts": detail["artifacts"]}
