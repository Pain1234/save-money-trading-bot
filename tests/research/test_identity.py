"""Tests for deterministic identity and immutable RunManifest (#142)."""

from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path

import pytest
from research.experiment_spec import load_experiment_spec, parse_experiment_spec
from research.identity import (
    RunIdentityInputs,
    compute_experiment_id,
    compute_run_id,
    new_attempt_id,
    semantic_artifact_hash,
    semantic_spec_dict,
)
from research.run_manifest import (
    build_run_manifest,
    load_run_manifest,
    save_run_manifest,
    semantic_manifest_payload,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
EXAMPLE_JSON = REPO_ROOT / "examples" / "research" / "btc_eth_sol_experiment.example.json"


def _inputs(**overrides: str) -> RunIdentityInputs:
    base = RunIdentityInputs(
        git_commit="abc123deadbeef",
        dataset_content_hash=(
            "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
        ),
        strategy_version="1.0.0",
        cost_model_version="cost-v1",
        metrics_schema_version="metrics-v1",
        environment_fingerprint="py3-test",
    )
    if not overrides:
        return base
    data = base.to_canonical_dict()
    data.update(overrides)
    return RunIdentityInputs(**data)


def test_same_semantic_spec_same_experiment_id() -> None:
    spec = load_experiment_spec(EXAMPLE_JSON)
    assert compute_experiment_id(spec) == compute_experiment_id(spec)


def test_owner_notes_do_not_change_experiment_id() -> None:
    import json

    data = json.loads(EXAMPLE_JSON.read_text(encoding="utf-8"))
    a = parse_experiment_spec(data)
    other = deepcopy(data)
    other["owner"] = "someone-else"
    other["notes"] = "changed notes must not affect identity"
    b = parse_experiment_spec(other)
    assert compute_experiment_id(a) == compute_experiment_id(b)
    assert "owner" not in semantic_spec_dict(a)
    assert "notes" not in semantic_spec_dict(a)


def test_semantic_change_changes_experiment_id() -> None:
    import json

    data = json.loads(EXAMPLE_JSON.read_text(encoding="utf-8"))
    a = parse_experiment_spec(data)
    other = deepcopy(data)
    other["hypothesis"] = "different hypothesis"
    b = parse_experiment_spec(other)
    assert compute_experiment_id(a) != compute_experiment_id(b)


def test_same_inputs_same_run_id() -> None:
    spec = load_experiment_spec(EXAMPLE_JSON)
    inputs = _inputs()
    assert compute_run_id(spec, inputs) == compute_run_id(spec, inputs)


def test_code_or_dataset_change_new_run_id() -> None:
    spec = load_experiment_spec(EXAMPLE_JSON)
    base = compute_run_id(spec, _inputs())
    assert compute_run_id(spec, _inputs(git_commit="ffffffffffff")) != base


def test_attempt_id_unique_for_retries() -> None:
    a = new_attempt_id()
    b = new_attempt_id()
    assert a != b
    assert a.startswith("att_")


def test_ci_double_run_semantic_hashes_stable() -> None:
    spec = load_experiment_spec(EXAMPLE_JSON)
    inputs = _inputs()
    m1 = build_run_manifest(
        spec,
        inputs=inputs,
        attempt_id=new_attempt_id(),
        created_at_utc=datetime(2026, 1, 1, tzinfo=UTC),
        status="complete",
    )
    m2 = build_run_manifest(
        spec,
        inputs=inputs,
        attempt_id=new_attempt_id(),
        created_at_utc=datetime(2026, 6, 1, tzinfo=UTC),
        status="complete",
    )
    assert m1.run_id == m2.run_id
    assert m1.attempt_id != m2.attempt_id
    h1 = semantic_artifact_hash(semantic_manifest_payload(m1))
    h2 = semantic_artifact_hash(semantic_manifest_payload(m2))
    assert h1 == h2


def test_run_manifest_overwrite_refused(tmp_path: Path) -> None:
    spec = load_experiment_spec(EXAMPLE_JSON)
    manifest = build_run_manifest(
        spec,
        inputs=_inputs(),
        attempt_id=new_attempt_id(),
        status="complete",
    )
    path = tmp_path / "run_manifest.json"
    save_run_manifest(manifest, path)
    loaded = load_run_manifest(path)
    assert loaded.run_id == manifest.run_id
    with pytest.raises(FileExistsError):
        save_run_manifest(manifest, path)


def test_run_id_rejects_dataset_mismatch() -> None:
    spec = load_experiment_spec(EXAMPLE_JSON)
    with pytest.raises(ValueError, match="dataset_content_hash"):
        compute_run_id(
            spec,
            _inputs(
                dataset_content_hash=(
                    "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
                    "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
                )
            ),
        )
