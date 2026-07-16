"""Tests for research runner, artifacts, and registry (#143/#145)."""

from __future__ import annotations

import json
from copy import deepcopy
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from backtester.models import HistoricalDataBundle
from research.artifacts import load_checksums, verify_checksums
from research.experiment_spec import parse_experiment_spec
from research.registry import ExperimentRegistry
from research.runner import RunRequest, run_experiment
from strategy_engine.models import Candle, Timeframe

REPO_ROOT = Path(__file__).resolve().parents[2]
EXAMPLE_JSON = REPO_ROOT / "examples" / "research" / "btc_eth_sol_experiment.example.json"


def _btc_spec():
    data = deepcopy(json.loads(EXAMPLE_JSON.read_text(encoding="utf-8")))
    data["symbols"] = ["BTC"]
    return parse_experiment_spec(data)


def _candle(symbol: str, day: int, price: str = "100") -> Candle:
    open_time = datetime(2024, 1, day, tzinfo=UTC)
    return Candle(
        symbol=symbol,
        timeframe=Timeframe.DAILY,
        open_time=open_time,
        close_time=open_time.replace(hour=23, minute=59, second=59),
        open=Decimal(price),
        high=Decimal(price),
        low=Decimal(price),
        close=Decimal(price),
        volume=Decimal("1000"),
        is_closed=True,
    )


def _bundle_btc() -> HistoricalDataBundle:
    symbol = "BTC"
    daily = tuple(_candle(symbol, d) for d in range(1, 29))
    weekly = (
        Candle(
            symbol=symbol,
            timeframe=Timeframe.WEEKLY,
            open_time=datetime(2023, 12, 25, tzinfo=UTC),
            close_time=datetime(2023, 12, 31, 23, 59, 59, tzinfo=UTC),
            open=Decimal("100"),
            high=Decimal("105"),
            low=Decimal("95"),
            close=Decimal("100"),
            volume=Decimal("5000"),
            is_closed=True,
        ),
    )
    monthly = (
        Candle(
            symbol=symbol,
            timeframe=Timeframe.MONTHLY,
            open_time=datetime(2023, 12, 1, tzinfo=UTC),
            close_time=datetime(2023, 12, 31, 23, 59, 59, tzinfo=UTC),
            open=Decimal("100"),
            high=Decimal("100"),
            low=Decimal("100"),
            close=Decimal("100"),
            volume=Decimal("20000"),
            is_closed=True,
        ),
    )
    return HistoricalDataBundle(
        daily={symbol: daily},
        weekly={symbol: weekly},
        monthly={symbol: monthly},
        funding={symbol: ()},
    )


def test_dry_run_identity(tmp_path: Path) -> None:
    outcome = run_experiment(
        RunRequest(
            spec=_btc_spec(),
            bundle=_bundle_btc(),
            artifacts_root=tmp_path,
            repo_root=REPO_ROOT,
            dry_run=True,
        )
    )
    assert outcome.status == "dry_run"
    assert outcome.run_id.startswith("run_")


def test_run_writes_artifacts_and_registry(tmp_path: Path) -> None:
    spec = _btc_spec()
    outcome = run_experiment(
        RunRequest(
            spec=spec,
            bundle=_bundle_btc(),
            artifacts_root=tmp_path,
            repo_root=REPO_ROOT,
            dry_run=False,
        )
    )
    assert outcome.status == "complete", outcome.error
    assert outcome.artifact_path is not None
    run_dir = outcome.artifact_path
    for name in (
        "experiment.json",
        "run_manifest.json",
        "metrics.json",
        "report.md",
        "trades.json",
        "equity.json",
        "events.jsonl",
        "checksums.json",
    ):
        assert (run_dir / name).is_file(), name
    verify_checksums(run_dir)

    again = run_experiment(
        RunRequest(
            spec=spec,
            bundle=_bundle_btc(),
            artifacts_root=tmp_path,
            repo_root=REPO_ROOT,
        )
    )
    assert again.status == "failed"
    assert again.error is not None

    registry = ExperimentRegistry(tmp_path)
    registry.register_complete(
        experiment_id=outcome.experiment_id,
        run_id=outcome.run_id,
        attempt_id=outcome.attempt_id,
        strategy_version=spec.strategy_version,
        dataset_version=spec.dataset_manifest_ref.dataset_id,
        cost_model_version="1.0",
        benchmark_ref=spec.benchmark,
        artifact_path=run_dir,
        checksums=load_checksums(run_dir),
    )
    listed = registry.list_entries()
    assert len(listed) == 1
    assert listed[0].run_id == outcome.run_id

    sidecar = registry.invalidate(
        outcome.run_id,
        reason="fixture correction",
        actor="test",
    )
    assert sidecar.is_file()
    manifest_bytes = (run_dir / "run_manifest.json").read_bytes()
    assert (run_dir / "run_manifest.json").read_bytes() == manifest_bytes
    assert registry.show(outcome.run_id).status == "invalidated"
