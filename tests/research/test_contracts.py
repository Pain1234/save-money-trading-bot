"""Tests for strategy resolver, costs, and metrics contracts (#148/#49/#144)."""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

import pytest
from research.costs import (
    COST_MODEL_VERSION,
    base_cost_scenario,
    cost_manifest_fields,
    cost_models_from_spec,
    require_cost_fields,
)
from research.experiment_spec import load_experiment_spec, parse_experiment_spec
from research.metrics_contract import (
    METRICS_SCHEMA_VERSION,
    ResearchMetrics,
    parse_benchmark_ref,
    render_report_md,
    save_metrics_and_report,
    validate_metrics_or_mark_invalid,
)
from research.strategy_resolver import (
    STRATEGY_INTERFACE_VERSION,
    catalog_strategy_ids,
    canonicalize_strategy_id,
    known_strategy_ids,
    resolve_strategy,
)
from strategy_engine.constants import STRATEGY_VERSION

REPO_ROOT = Path(__file__).resolve().parents[2]
EXAMPLE_JSON = REPO_ROOT / "examples" / "research" / "btc_eth_sol_experiment.example.json"


def test_resolve_trend_v1() -> None:
    spec = load_experiment_spec(EXAMPLE_JSON)
    resolved = resolve_strategy(spec)
    assert resolved.strategy_id == "trend_v1"
    assert resolved.strategy_version == STRATEGY_VERSION
    assert resolved.interface_version == STRATEGY_INTERFACE_VERSION
    assert resolved.entrypoint.endswith("StrategyEngine")


def test_resolve_alias_trend_strategy_v1() -> None:
    data = json.loads(EXAMPLE_JSON.read_text(encoding="utf-8"))
    data["parameters"] = {**data["parameters"], "strategy_id": "trend_strategy_v1"}
    spec = parse_experiment_spec(data)
    resolved = resolve_strategy(spec)
    assert resolved.strategy_id == "trend_v1"


def test_catalog_lists_canonical_once() -> None:
    assert catalog_strategy_ids() == ("trend_v1",)
    assert "trend_strategy_v1" in known_strategy_ids()
    assert canonicalize_strategy_id("trend_strategy_v1") == "trend_v1"


def test_unknown_strategy_fails() -> None:
    data = json.loads(EXAMPLE_JSON.read_text(encoding="utf-8"))
    data["parameters"] = {**data["parameters"], "strategy_id": "nope"}
    spec = parse_experiment_spec(data)
    with pytest.raises(ValueError, match="unknown strategy_id"):
        resolve_strategy(spec)


def test_cost_models_from_example() -> None:
    spec = load_experiment_spec(EXAMPLE_JSON)
    require_cost_fields(spec)
    fee, slip, funding = cost_models_from_spec(spec)
    assert fee.entry_fee_rate == Decimal("0.0005")
    assert slip.slippage_bps == Decimal("5")
    assert funding.enabled is False
    scenario = base_cost_scenario(spec)
    assert scenario.name == "base"
    fields = cost_manifest_fields(spec)
    assert fields["cost_model_version"] == COST_MODEL_VERSION


def test_benchmark_ref_and_metrics_roundtrip(tmp_path: Path) -> None:
    ref = parse_benchmark_ref("buy_and_hold_BTC")
    assert ref.benchmark_id == "buy_and_hold_BTC"
    assert ref.benchmark_version == "1.0"
    ref = ref.model_copy(
        update={
            "cost_model_version": "1.1",
            "gross_return": Decimal("0.08"),
        }
    )
    metrics = ResearchMetrics(
        start_capital=Decimal("100000"),
        end_capital=Decimal("110000"),
        gross_pnl=Decimal("10500"),
        net_pnl=Decimal("10000"),
        fees=Decimal("400"),
        slippage_costs=Decimal("100"),
        funding_assumption="disabled",
        signal_count=10,
        order_count=10,
        fill_count=10,
        closed_trades=5,
        hit_rate=Decimal("0.6"),
        avg_win=Decimal("2000"),
        avg_loss=Decimal("-500"),
        expectancy=Decimal("500"),
        profit_factor=Decimal("2.0"),
        max_drawdown=Decimal("0.1"),
        exposure=Decimal("0.5"),
        turnover=Decimal("1.2"),
        time_in_market=Decimal("0.4"),
        benchmark=ref,
        benchmark_result=Decimal("0.08"),
    )
    assert metrics.schema_version == METRICS_SCHEMA_VERSION
    report = render_report_md(metrics)
    assert "gross_pnl" in report and "net_pnl" in report
    mpath = tmp_path / "metrics.json"
    rpath = tmp_path / "report.md"
    save_metrics_and_report(metrics, mpath, rpath)
    loaded = validate_metrics_or_mark_invalid(
        json.loads(mpath.read_text(encoding="utf-8"))
    )
    assert loaded.net_pnl == Decimal("10000")


def test_missing_benchmark_fails_validation() -> None:
    with pytest.raises(ValueError):
        parse_benchmark_ref("")


def test_funding_enabled_requires_rate() -> None:
    data = json.loads(EXAMPLE_JSON.read_text(encoding="utf-8"))
    data["funding_assumption"] = {
        "enabled": True,
        "assumed_rate": None,
        "model_version": "1.0",
    }
    spec = parse_experiment_spec(data)
    with pytest.raises(ValueError, match="assumed_rate"):
        require_cost_fields(spec)


def test_funding_rate_mapped_to_backtester_model() -> None:
    data = json.loads(EXAMPLE_JSON.read_text(encoding="utf-8"))
    data["funding_assumption"] = {
        "enabled": True,
        "assumed_rate": "0.0001",
        "model_version": "1.0",
    }
    spec = parse_experiment_spec(data)
    _fee, _slip, funding = cost_models_from_spec(spec)
    assert funding.enabled is True
    assert funding.assumed_rate == Decimal("0.0001")
    fields = cost_manifest_fields(spec)
    assert fields["fee_model_version"] == "1.0"
    assert fields["funding_assumed_rate"] == "0.0001"

