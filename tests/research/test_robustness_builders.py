"""Unit tests for robustness child-spec builders (Issue #247 / P4.7b).

Pure computation over Specs/artifacts — no backtest engine invocation here.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from research.robustness import (
    build_cost_stress_child_specs,
    build_parameter_stability_child_specs,
    build_walk_forward_child_specs,
    compute_bootstrap_from_equity_artifact,
    compute_robustness_id,
    period_pnl_series_from_equity,
    robustness_artifact_dir,
    robustness_manifest_path,
)

from tests.research.fixtures import align_spec_to_bundle, btc_bundle


def _base_spec(tmp_path: Path):
    bundle = btc_bundle()
    return align_spec_to_bundle(tmp_path, bundle, symbols=["BTC"])


def test_build_walk_forward_child_specs_tiles_eval_windows(tmp_path: Path) -> None:
    spec = _base_spec(tmp_path)
    children = build_walk_forward_child_specs(
        spec, n_folds=2, embargo_days=0, feature_warmup_monthly_bars=1
    )
    assert [c.child_id for c in children] == ["fold_01", "fold_02"]
    # Each fold's Spec keeps the base dataset ref/parameters; only the window changes.
    for child in children:
        assert child.spec.dataset_manifest_ref == spec.dataset_manifest_ref
        assert child.spec.parameters == spec.parameters
        assert child.spec.time_range.start >= spec.time_range.start
        assert child.spec.time_range.end <= spec.time_range.end
        assert "[walk_forward:" in child.spec.hypothesis
    # Fold windows are chronological and non-overlapping on eval boundaries.
    assert children[0].spec.time_range.end < children[1].spec.time_range.end


def test_build_walk_forward_rejects_insufficient_warmup(tmp_path: Path) -> None:
    spec = _base_spec(tmp_path)
    with pytest.raises(ValueError, match="warmup"):
        build_walk_forward_child_specs(
            spec, n_folds=2, embargo_days=0, feature_warmup_monthly_bars=20
        )


def test_build_cost_stress_child_specs_covers_all_scenarios(tmp_path: Path) -> None:
    spec = _base_spec(tmp_path)
    children = build_cost_stress_child_specs(spec)
    names = [c.child_id for c in children]
    assert names == [
        "base",
        "fee_x2",
        "slippage_x2",
        "funding_stress",
        "combined_elevated",
        "combined_extreme",
    ]
    base_child = next(c for c in children if c.child_id == "base")
    assert base_child.spec.fee_assumption.entry_fee_rate == spec.fee_assumption.entry_fee_rate
    fee_x2 = next(c for c in children if c.child_id == "fee_x2")
    assert fee_x2.spec.fee_assumption.entry_fee_rate == spec.fee_assumption.entry_fee_rate * 2
    # Only cost assumptions change; dataset/time_range/parameters stay pinned.
    for child in children:
        assert child.spec.time_range == spec.time_range
        assert child.spec.parameters == spec.parameters


def test_build_parameter_stability_child_specs_default_neighborhood(tmp_path: Path) -> None:
    spec = _base_spec(tmp_path)
    children = build_parameter_stability_child_specs(spec)
    assert children[0].child_id == "frozen"
    assert children[0].label == "baseline"
    assert children[0].spec.parameters == spec.parameters
    # One-at-a-time: every non-frozen variant differs in exactly one parameter.
    for child in children[1:]:
        diffs = [
            key
            for key in spec.parameters
            if key != "strategy_id" and child.spec.parameters.get(key) != spec.parameters.get(key)
        ]
        assert len(diffs) == 1
        assert diffs[0] in child.label


def test_build_parameter_stability_child_specs_custom_neighborhood(tmp_path: Path) -> None:
    spec = _base_spec(tmp_path)
    children = build_parameter_stability_child_specs(
        spec,
        int_deltas={"atr_period": (-1, 1)},
        # Empty-but-falsy dicts fall back to defaults in symmetric_neighborhood, so an
        # unmatched key is used here to isolate the neighborhood to atr_period only.
        decimal_relative_steps={"_unused": ("0.1",)},
    )
    assert len(children) == 3  # frozen + 2 neighbors
    assert {c.spec.parameters["atr_period"] for c in children} == {
        spec.parameters["atr_period"],
        spec.parameters["atr_period"] - 1,
        spec.parameters["atr_period"] + 1,
    }


def test_period_pnl_series_from_equity_is_chronological_diff() -> None:
    points = [
        {"time": "2024-01-03T00:00:00Z", "equity": "110"},
        {"time": "2024-01-01T00:00:00Z", "equity": "100"},
        {"time": "2024-01-02T00:00:00Z", "equity": "105"},
    ]
    series = period_pnl_series_from_equity(points)
    assert series == [5.0, 5.0]


def test_compute_bootstrap_from_equity_artifact_uses_path_bootstrap(tmp_path: Path) -> None:
    import json

    run_dir = tmp_path / "run"
    run_dir.mkdir()
    equity = [
        {"time": f"2024-01-{d:02d}T00:00:00Z", "equity": str(100 + d)} for d in range(1, 11)
    ]
    (run_dir / "equity.json").write_text(json.dumps(equity), encoding="utf-8")

    result = compute_bootstrap_from_equity_artifact(
        run_dir, block_length=2, n_simulations=50, seed=42
    )
    assert result.n_simulations == 50
    assert result.block_length == 2
    assert set(result.net_pnl_quantiles) == {"q05", "q50", "q95"}


def test_compute_bootstrap_from_equity_artifact_missing_file_fails_closed(
    tmp_path: Path,
) -> None:
    with pytest.raises(FileNotFoundError):
        compute_bootstrap_from_equity_artifact(
            tmp_path, block_length=2, n_simulations=10, seed=1
        )


def test_compute_robustness_id_is_deterministic_and_config_sensitive() -> None:
    a = compute_robustness_id(
        base_experiment_id="exp_a",
        test_type="walk_forward",
        config={"n_folds": 3, "embargo_days": 90, "feature_warmup_monthly_bars": 20},
        dataset_catalog_id="local-btc-fixture",
        base_run_id="run_x",
    )
    b = compute_robustness_id(
        base_experiment_id="exp_a",
        test_type="walk_forward",
        config={"n_folds": 3, "embargo_days": 90, "feature_warmup_monthly_bars": 20},
        dataset_catalog_id="local-btc-fixture",
        base_run_id="run_x",
    )
    c = compute_robustness_id(
        base_experiment_id="exp_a",
        test_type="walk_forward",
        config={"n_folds": 4, "embargo_days": 90, "feature_warmup_monthly_bars": 20},
        dataset_catalog_id="local-btc-fixture",
        base_run_id="run_x",
    )
    assert a == b
    assert a != c
    assert a.startswith("rob_")


def test_robustness_artifact_paths(tmp_path: Path) -> None:
    assert robustness_artifact_dir(tmp_path, "rob_x") == (
        tmp_path / "artifacts" / "research" / "robustness" / "rob_x"
    )
    assert robustness_manifest_path(tmp_path, "rob_x") == (
        tmp_path / "artifacts" / "research" / "robustness" / "rob_x" / "manifest.json"
    )
