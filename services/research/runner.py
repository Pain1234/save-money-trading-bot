"""Deterministic research runner (Issue #143 / P4-03)."""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from backtester.engine import BacktestEngine
from backtester.models import BacktestConfig, BacktestResult, HistoricalDataBundle
from strategy_engine.models import StrategyParameters

from research.artifacts import ArtifactWriter, artifact_dir
from research.benchmark import compute_benchmark_result
from research.costs import COST_MODEL_VERSION, cost_models_from_spec, require_cost_fields
from research.experiment_spec import (
    ExperimentSpec,
    dumps_canonical,
    load_experiment_spec,
    parse_experiment_spec,
    to_canonical_dict,
)
from research.identity import RunIdentityInputs, new_attempt_id
from research.metrics_contract import (
    METRICS_SCHEMA_VERSION,
    ResearchMetrics,
    save_metrics_and_report,
)
from research.run_manifest import build_run_manifest, dumps_run_manifest
from research.strategy_resolver import resolve_strategy


def _git_commit(repo_root: Path) -> str:
    try:
        out = subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=repo_root,
            stderr=subprocess.DEVNULL,
            text=True,
        )
        return out.strip()
    except (subprocess.CalledProcessError, FileNotFoundError, OSError):
        return "unknown"


def _environment_fingerprint() -> str:
    import platform
    import sys

    return f"{sys.version_info.major}.{sys.version_info.minor}-{platform.system()}"


@dataclass(frozen=True)
class RunRequest:
    spec: ExperimentSpec
    bundle: HistoricalDataBundle
    artifacts_root: Path
    repo_root: Path
    dry_run: bool = False


@dataclass(frozen=True)
class RunOutcome:
    experiment_id: str
    run_id: str
    attempt_id: str
    artifact_path: Path | None
    status: str
    error: str | None = None


def _config_from_spec(spec: ExperimentSpec, params: StrategyParameters) -> BacktestConfig:
    fee, slip, funding = cost_models_from_spec(spec)
    symbols = tuple(s.value for s in spec.symbols)
    return BacktestConfig(
        symbols=symbols,
        initial_cash=spec.starting_capital,
        strategy_params=params,
        fee_model=fee,
        slippage_model=slip,
        funding_model=funding,
    )


def _metrics_from_result(
    spec: ExperimentSpec,
    result: BacktestResult,
    bundle: HistoricalDataBundle,
) -> ResearchMetrics:
    m = result.metrics
    funding_assumption = (
        f"enabled:{spec.funding_assumption.assumed_rate}"
        if spec.funding_assumption.enabled
        else "disabled"
    )
    end_capital = result.end_capital
    net_pnl = end_capital - spec.starting_capital
    gross_pnl = net_pnl + result.total_fees + result.total_slippage
    benchmark_ref, benchmark_result = compute_benchmark_result(spec, bundle)
    return ResearchMetrics(
        start_capital=spec.starting_capital,
        end_capital=end_capital,
        gross_pnl=gross_pnl,
        net_pnl=net_pnl,
        fees=result.total_fees,
        slippage_costs=result.total_slippage,
        funding_assumption=funding_assumption,
        signal_count=len(result.strategy_evaluations),
        order_count=len(result.trades),
        fill_count=len(result.trades),
        closed_trades=m.trade_count,
        hit_rate=m.win_rate,
        avg_win=m.average_winner,
        avg_loss=m.average_loser,
        expectancy=m.expectancy_usd,
        profit_factor=m.profit_factor,
        max_drawdown=m.max_drawdown_pct,
        exposure=None,
        turnover=None,
        time_in_market=m.time_in_market_pct,
        benchmark=benchmark_ref,
        benchmark_result=benchmark_result,
    )


def run_experiment(request: RunRequest) -> RunOutcome:
    """Validate, execute, and atomically persist a research run."""
    spec = request.spec
    require_cost_fields(spec)
    resolved = resolve_strategy(spec)
    attempt_id = new_attempt_id()
    inputs = RunIdentityInputs(
        git_commit=_git_commit(request.repo_root),
        dataset_content_hash=spec.dataset_manifest_ref.content_hash,
        strategy_version=spec.strategy_version,
        cost_model_version=COST_MODEL_VERSION,
        metrics_schema_version=METRICS_SCHEMA_VERSION,
        environment_fingerprint=_environment_fingerprint(),
    )
    draft = build_run_manifest(
        spec,
        inputs=inputs,
        attempt_id=attempt_id,
        created_at_utc=datetime.now(UTC),
        status="incomplete",
    )
    final_dir = artifact_dir(
        request.artifacts_root,
        draft.experiment_id,
        draft.run_id,
    )
    if request.dry_run:
        return RunOutcome(
            experiment_id=draft.experiment_id,
            run_id=draft.run_id,
            attempt_id=attempt_id,
            artifact_path=None,
            status="dry_run",
        )
    try:
        with ArtifactWriter(final_dir) as writer:
            assert writer.work_dir is not None
            writer.write_bytes("experiment.json", dumps_canonical(spec) + b"\n")
            config = _config_from_spec(spec, resolved.parameters)
            result = BacktestEngine().run(request.bundle, config)
            metrics = _metrics_from_result(spec, result, request.bundle)
            complete = build_run_manifest(
                spec,
                inputs=inputs,
                attempt_id=attempt_id,
                created_at_utc=datetime.now(UTC),
                status="complete",
            )
            writer.write_bytes("run_manifest.json", dumps_run_manifest(complete) + b"\n")
            save_metrics_and_report(
                metrics,
                writer.work_dir / "metrics.json",
                writer.work_dir / "report.md",
            )
            trades_payload: list[dict[str, Any]] = [
                json.loads(t.model_dump_json()) for t in result.trades
            ]
            writer.write_json("trades.json", trades_payload)
            equity_payload = [json.loads(e.model_dump_json()) for e in result.equity_curve]
            writer.write_json("equity.json", equity_payload)
            events = [
                {
                    "type": "evaluation",
                    "symbol": ev.symbol,
                    "time": ev.evaluation_time.isoformat(),
                }
                for ev in result.strategy_evaluations
            ]
            writer.write_text(
                "events.jsonl",
                "".join(json.dumps(e, sort_keys=True) + "\n" for e in events),
            )
            writer.finalize()
        return RunOutcome(
            experiment_id=draft.experiment_id,
            run_id=draft.run_id,
            attempt_id=attempt_id,
            artifact_path=final_dir,
            status="complete",
        )
    except FileExistsError as exc:
        return RunOutcome(
            experiment_id=draft.experiment_id,
            run_id=draft.run_id,
            attempt_id=attempt_id,
            artifact_path=final_dir,
            status="failed",
            error=str(exc),
        )
    except Exception as exc:  # noqa: BLE001 — surface structured failure
        return RunOutcome(
            experiment_id=draft.experiment_id,
            run_id=draft.run_id,
            attempt_id=attempt_id,
            artifact_path=None,
            status="failed",
            error=str(exc),
        )


def validate_spec_path(path: Path) -> ExperimentSpec:
    return load_experiment_spec(path, check_json_schema=True)


def inspect_run(run_dir: Path) -> dict[str, Any]:
    manifest = json.loads((run_dir / "run_manifest.json").read_text(encoding="utf-8"))
    metrics = json.loads((run_dir / "metrics.json").read_text(encoding="utf-8"))
    experiment = parse_experiment_spec(
        json.loads((run_dir / "experiment.json").read_text(encoding="utf-8"))
    )
    return {
        "path": str(run_dir),
        "manifest": manifest,
        "metrics": metrics,
        "experiment": to_canonical_dict(experiment),
    }
