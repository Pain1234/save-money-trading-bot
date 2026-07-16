"""Real double-run semantic artifact gate (#146)."""

from __future__ import annotations

import json
from copy import deepcopy
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest
from backtester.models import HistoricalDataBundle
from research.experiment_spec import parse_experiment_spec
from research.identity import semantic_artifact_hash
from research.repro import compare_semantic_run_dirs, semantic_manifest_from_file
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


def test_double_run_semantic_hashes_match(tmp_path: Path) -> None:
    """Two runs, different artifacts_root → same semantic metrics/trades hashes."""
    spec = _btc_spec()
    bundle = _bundle_btc()
    root_a = tmp_path / "a"
    root_b = tmp_path / "b"

    out_a = run_experiment(
        RunRequest(
            spec=spec,
            bundle=bundle,
            artifacts_root=root_a,
            repo_root=REPO_ROOT,
        )
    )
    out_b = run_experiment(
        RunRequest(
            spec=spec,
            bundle=bundle,
            artifacts_root=root_b,
            repo_root=REPO_ROOT,
        )
    )
    assert out_a.status == "complete", out_a.error
    assert out_b.status == "complete", out_b.error
    assert out_a.run_id == out_b.run_id
    assert out_a.attempt_id != out_b.attempt_id
    assert out_a.artifact_path is not None
    assert out_b.artifact_path is not None

    hashes = compare_semantic_run_dirs(out_a.artifact_path, out_b.artifact_path)
    assert "metrics.json" in hashes
    assert "trades.json" in hashes

    # Manifests differ on attempt_id / timestamps but share semantic hash.
    m_a = json.loads(
        (out_a.artifact_path / "run_manifest.json").read_text(encoding="utf-8")
    )
    m_b = json.loads(
        (out_b.artifact_path / "run_manifest.json").read_text(encoding="utf-8")
    )
    assert m_a["attempt_id"] != m_b["attempt_id"]
    assert semantic_artifact_hash(
        semantic_manifest_from_file(out_a.artifact_path / "run_manifest.json")
    ) == semantic_artifact_hash(
        semantic_manifest_from_file(out_b.artifact_path / "run_manifest.json")
    )


def test_same_root_second_run_refuses_overwrite(tmp_path: Path) -> None:
    spec = _btc_spec()
    bundle = _bundle_btc()
    first = run_experiment(
        RunRequest(
            spec=spec,
            bundle=bundle,
            artifacts_root=tmp_path,
            repo_root=REPO_ROOT,
        )
    )
    assert first.status == "complete", first.error
    second = run_experiment(
        RunRequest(
            spec=spec,
            bundle=bundle,
            artifacts_root=tmp_path,
            repo_root=REPO_ROOT,
        )
    )
    assert second.status == "failed"
    assert second.error is not None
    assert "overwrite" in second.error.lower() or "exists" in second.error.lower()


def test_compare_detects_divergence(tmp_path: Path) -> None:
    spec = _btc_spec()
    bundle = _bundle_btc()
    out = run_experiment(
        RunRequest(
            spec=spec,
            bundle=bundle,
            artifacts_root=tmp_path / "ok",
            repo_root=REPO_ROOT,
        )
    )
    assert out.status == "complete" and out.artifact_path is not None
    twin = tmp_path / "tampered"
    twin.mkdir(parents=True)
    for name in (
        "metrics.json",
        "trades.json",
        "equity.json",
        "costs.json",
        "experiment.json",
        "run_manifest.json",
    ):
        (twin / name).write_bytes((out.artifact_path / name).read_bytes())
    metrics = json.loads((twin / "metrics.json").read_text(encoding="utf-8"))
    metrics["net_pnl"] = "999999"
    (twin / "metrics.json").write_text(
        json.dumps(metrics, sort_keys=True) + "\n", encoding="utf-8"
    )
    with pytest.raises(ValueError, match="semantic hash mismatch"):
        compare_semantic_run_dirs(out.artifact_path, twin)
