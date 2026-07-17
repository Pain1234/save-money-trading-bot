"""Adversarial dataset binding tests (#163)."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest
from backtester.models import FundingEvent
from research.dataset_binding import (
    bind_dataset_to_bundle,
    filter_bundle_to_time_range,
    hash_research_bundle,
)
from research.experiment_spec import TimeRange
from research.runner import RunRequest, run_experiment

from tests.research.fixtures import (
    REPO_ROOT,
    align_spec_to_bundle,
    btc_bundle,
    research_time_range,
)


def test_mismatched_bundle_rejected(tmp_path: Path) -> None:
    matching = btc_bundle(price="100")
    other = btc_bundle(price="200")
    spec = align_spec_to_bundle(tmp_path, matching)
    outcome = run_experiment(
        RunRequest(
            spec=spec,
            bundle=other,
            artifacts_root=tmp_path / "out",
            repo_root=REPO_ROOT,
            allow_dirty_git=True,
        )
    )
    assert outcome.status == "failed"
    assert outcome.artifact_path is None
    assert outcome.error is not None
    assert "content_hash" in outcome.error.lower() or "does not match" in outcome.error


def test_same_declared_ref_different_bundles_no_shared_complete_run(
    tmp_path: Path,
) -> None:
    a = btc_bundle(price="100")
    b = btc_bundle(price="111")
    spec = align_spec_to_bundle(tmp_path, a)
    out_a = run_experiment(
        RunRequest(
            spec=spec,
            bundle=a,
            artifacts_root=tmp_path / "a",
            repo_root=REPO_ROOT,
            allow_dirty_git=True,
        )
    )
    out_b = run_experiment(
        RunRequest(
            spec=spec,
            bundle=b,
            artifacts_root=tmp_path / "b",
            repo_root=REPO_ROOT,
            allow_dirty_git=True,
        )
    )
    assert out_a.status == "complete", out_a.error
    assert out_b.status == "failed", out_b.error
    assert out_b.artifact_path is None


def test_bind_applies_experiment_time_range(tmp_path: Path) -> None:
    bundle = btc_bundle(end_day=28)
    manifest_tr = research_time_range()
    exp_tr = TimeRange(
        start=datetime(2024, 1, 1, tzinfo=UTC),
        end=datetime(2024, 1, 10, 23, 59, 59, tzinfo=UTC),
    )
    spec = align_spec_to_bundle(
        tmp_path,
        bundle,
        time_range=manifest_tr,
        experiment_time_range=exp_tr,
    )
    _manifest, filtered, digest = bind_dataset_to_bundle(
        spec, bundle, repo_root=REPO_ROOT
    )
    assert digest == spec.dataset_manifest_ref.content_hash
    full_hash = hash_research_bundle(
        filter_bundle_to_time_range(bundle, manifest_tr, ("BTC",)),
        ("BTC",),
    )
    assert digest == full_hash
    assert digest != hash_research_bundle(filtered, ("BTC",))
    for c in filtered.daily["BTC"]:
        assert exp_tr.start <= c.open_time <= exp_tr.end
    assert len(filtered.daily["BTC"]) == 10


def test_invalid_manifest_rejected(tmp_path: Path) -> None:
    bundle = btc_bundle()
    spec = align_spec_to_bundle(tmp_path, bundle, quality_status="INVALID")
    with pytest.raises(ValueError, match="quarantined"):
        bind_dataset_to_bundle(spec, bundle, repo_root=REPO_ROOT)


def test_stale_without_allow_warnings_rejected(tmp_path: Path) -> None:
    bundle = btc_bundle()
    spec = align_spec_to_bundle(
        tmp_path,
        bundle,
        quality_status="STALE",
        allow_quality_warnings=False,
    )
    with pytest.raises(ValueError, match="allow_quality_warnings"):
        bind_dataset_to_bundle(spec, bundle, repo_root=REPO_ROOT)


def test_funding_change_outside_dataset_hash(tmp_path: Path) -> None:
    bundle = btc_bundle()
    funded = bundle.model_copy(
        update={
            "funding": {
                "BTC": (
                    FundingEvent(
                        timestamp=datetime(2024, 1, 5, 12, tzinfo=UTC),
                        funding_rate=Decimal("0.001"),
                    ),
                )
            }
        }
    )
    spec = align_spec_to_bundle(tmp_path, bundle)
    # Same candle content → same content_hash; funding ignored in hash.
    _m, _f, digest = bind_dataset_to_bundle(spec, funded, repo_root=REPO_ROOT)
    assert digest == spec.dataset_manifest_ref.content_hash
    outcome = run_experiment(
        RunRequest(
            spec=spec,
            bundle=funded,
            artifacts_root=tmp_path / "out",
            repo_root=REPO_ROOT,
            allow_dirty_git=True,
        )
    )
    assert outcome.status == "complete", outcome.error
