"""Fail-closed sealed artifact content GET (#357)."""

from __future__ import annotations

import hashlib
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import quote

import pytest
from fastapi.testclient import TestClient
from paper_trading.readonly_api import app
from research.api import get_scorecard_service
from research.artifact_content import ArtifactContentError, normalize_relative_path
from research.artifacts import compute_artifact_checksums, load_checksums
from research.registry import ExperimentRegistry
from research.scorecard_evaluator import ScorecardResultStore
from research.scorecard_service import ScorecardService

from tests.research import test_gate_evaluator as te


@pytest.fixture(autouse=True)
def _pin_evaluation_git_sha(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RESEARCH_EVALUATION_GIT_SHA", "a" * 40)
    monkeypatch.delenv("RAILWAY_GIT_COMMIT_SHA", raising=False)


def _evaluator(root: Path):
    from research.scorecard_evaluator import ScorecardEvaluator

    return ScorecardEvaluator(root, repo_root=te._evaluation_image_root(root))


def _client_for(root: Path) -> TestClient:
    def _scorecard() -> ScorecardService:
        return ScorecardService(root, repo_root=te._evaluation_image_root(root))

    app.dependency_overrides[get_scorecard_service] = _scorecard
    return TestClient(app)


def _evaluate(root: Path, run_id: str) -> str:
    record = _evaluator(root).evaluate(run_id=run_id, policy_version="1.0")
    return record.scorecard_id


def _content_url(scorecard_id: str, relative_path: str) -> str:
    return (
        f"/api/v1/research/scorecards/{scorecard_id}/artifacts/content"
        f"?relative_path={quote(relative_path, safe='')}"
    )


def test_normalize_rejects_traversal_and_absolute() -> None:
    with pytest.raises(ArtifactContentError) as exc:
        normalize_relative_path("../secrets.json")
    assert exc.value.code == "not_allowlisted"

    with pytest.raises(ArtifactContentError) as exc2:
        normalize_relative_path("/etc/passwd")
    assert exc2.value.code == "not_allowlisted"

    with pytest.raises(ArtifactContentError) as exc3:
        normalize_relative_path("C:/Windows/system32")
    assert exc3.value.code == "not_allowlisted"

    with pytest.raises(ArtifactContentError) as exc4:
        normalize_relative_path("foo%2fbar.json")
    assert exc4.value.code == "not_allowlisted"

    with pytest.raises(ArtifactContentError) as exc5:
        normalize_relative_path("a\x00b.json")
    assert exc5.value.code == "not_allowlisted"


def test_valid_sealed_json_content(tmp_path: Path) -> None:
    root, _exp, run_id = te._completed_run(tmp_path)
    sid = _evaluate(root, run_id)
    client = _client_for(root)
    try:
        resp = client.get(_content_url(sid, "regime_metrics.json"))
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["scorecard_id"] == sid
        assert body["relative_path"] == "regime_metrics.json"
        assert body["content_type"] == "application/json"
        assert isinstance(body["content"], dict)
        assert "regimes" in body["content"]
        assert len(body["checksum_sha256"]) == 64
        assert resp.headers.get("x-content-type-options") == "nosniff"
        assert str(root.resolve()) not in resp.text
    finally:
        app.dependency_overrides.pop(get_scorecard_service, None)


def test_valid_text_content(tmp_path: Path) -> None:
    root, _exp, run_id = te._completed_run(tmp_path)
    entry = ExperimentRegistry(root).show(run_id, verify=True)
    src_dir = Path(entry.artifact_path)
    new_run_id = f"{run_id}_txt"
    dst_dir = src_dir.parent / new_run_id
    import shutil

    shutil.copytree(src_dir, dst_dir)
    text_name = "notes.txt"
    text_body = "sealed forensic note\n"
    (dst_dir / text_name).write_bytes(text_body.encode("utf-8"))
    checksums = compute_artifact_checksums(dst_dir)
    (dst_dir / "checksums.json").write_text(
        json.dumps(checksums, sort_keys=True) + "\n", encoding="utf-8"
    )
    ExperimentRegistry(root).register_complete(
        experiment_id=entry.experiment_id,
        run_id=new_run_id,
        attempt_id=f"{new_run_id}_attempt",
        strategy_version=entry.strategy_version,
        dataset_version=entry.dataset_version,
        cost_model_version=entry.cost_model_version,
        benchmark_ref=entry.benchmark_ref,
        artifact_path=dst_dir,
        checksums=checksums,
    )

    sid = _evaluate(root, new_run_id)
    client = _client_for(root)
    try:
        resp = client.get(_content_url(sid, text_name))
        assert resp.status_code == 200, resp.text
        assert "text/plain" in (resp.headers.get("content-type") or "")
        assert resp.text == text_body
        assert resp.headers.get("x-artifact-relative-path") == text_name
    finally:
        app.dependency_overrides.pop(get_scorecard_service, None)


def test_missing_file(tmp_path: Path) -> None:
    root, _exp, run_id = te._completed_run(tmp_path)
    sid = _evaluate(root, run_id)
    entry = ExperimentRegistry(root).show(run_id, verify=False)
    target = Path(entry.artifact_path) / "regime_metrics.json"
    assert target.is_file()
    target.unlink()

    client = _client_for(root)
    try:
        resp = client.get(_content_url(sid, "regime_metrics.json"))
        assert resp.status_code == 404
        assert resp.json()["detail"]["code"] == "not_found"
    finally:
        app.dependency_overrides.pop(get_scorecard_service, None)


def test_missing_manifest_entry(tmp_path: Path) -> None:
    root, _exp, run_id = te._completed_run(tmp_path)
    sid = _evaluate(root, run_id)
    client = _client_for(root)
    try:
        resp = client.get(_content_url(sid, "not_in_manifest.json"))
        assert resp.status_code == 404
        assert resp.json()["detail"]["code"] in {"not_pinned", "not_allowlisted"}
    finally:
        app.dependency_overrides.pop(get_scorecard_service, None)


def test_checksum_mismatch(tmp_path: Path) -> None:
    root, _exp, run_id = te._completed_run(tmp_path)
    sid = _evaluate(root, run_id)
    entry = ExperimentRegistry(root).show(run_id, verify=False)
    path = Path(entry.artifact_path) / "regime_metrics.json"
    path.write_text('{"tampered":true}\n', encoding="utf-8")

    client = _client_for(root)
    try:
        resp = client.get(_content_url(sid, "regime_metrics.json"))
        assert resp.status_code == 409
        assert resp.json()["detail"]["code"] == "checksum_mismatch"
    finally:
        app.dependency_overrides.pop(get_scorecard_service, None)


def test_incomplete_run(tmp_path: Path) -> None:
    root, exp_id, run_id = te._completed_run(tmp_path)
    sid = _evaluate(root, run_id)
    entry = ExperimentRegistry(root).show(run_id, verify=False)
    registry = ExperimentRegistry(root)
    registry._append(
        {
            "experiment_id": exp_id,
            "run_id": run_id,
            "attempt_id": f"{entry.attempt_id}_fail",
            "status": "failed",
            "strategy_version": entry.strategy_version,
            "dataset_version": entry.dataset_version,
            "cost_model_version": entry.cost_model_version,
            "benchmark_ref": entry.benchmark_ref,
            "created_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
            "artifact_path": entry.artifact_path,
            "checksums": {},
        }
    )

    client = _client_for(root)
    try:
        resp = client.get(_content_url(sid, "regime_metrics.json"))
        assert resp.status_code == 409
        assert resp.json()["detail"]["code"] == "unsealed_run"
    finally:
        app.dependency_overrides.pop(get_scorecard_service, None)


def test_invalidated_scorecard(tmp_path: Path) -> None:
    root, _exp, run_id = te._completed_run(tmp_path)
    sid = _evaluate(root, run_id)
    ScorecardResultStore(root).invalidate(sid, reason="fixture", actor="test")

    client = _client_for(root)
    try:
        resp = client.get(_content_url(sid, "regime_metrics.json"))
        assert resp.status_code == 409
        assert resp.json()["detail"]["code"] == "invalidated_evidence"
    finally:
        app.dependency_overrides.pop(get_scorecard_service, None)


@pytest.mark.parametrize(
    "bad_path",
    [
        "../regime_metrics.json",
        "..\\regime_metrics.json",
        "/etc/passwd",
        "C:/Windows/win.ini",
        quote("../regime_metrics.json", safe=""),
        quote(quote("../x.json", safe=""), safe=""),
    ],
)
def test_path_traversal_rejected(tmp_path: Path, bad_path: str) -> None:
    root, _exp, run_id = te._completed_run(tmp_path)
    sid = _evaluate(root, run_id)
    client = _client_for(root)
    try:
        resp = client.get(
            f"/api/v1/research/scorecards/{sid}/artifacts/content",
            params={"relative_path": bad_path},
        )
        assert resp.status_code in {400, 404}
        detail = resp.json()["detail"]
        assert isinstance(detail, dict)
        assert detail["code"] in {"not_allowlisted", "not_pinned", "not_found"}
        assert resp.status_code != 200
    finally:
        app.dependency_overrides.pop(get_scorecard_service, None)


def test_symlink_out_of_run_dir(tmp_path: Path) -> None:
    root, _exp, run_id = te._completed_run(tmp_path)
    entry = ExperimentRegistry(root).show(run_id, verify=True)
    run_dir = Path(entry.artifact_path)

    # Evaluate while the run dir is still clean — adding an untracked symlink
    # *before* evaluate breaks registry checksum verify (CI Linux).
    sid = _evaluate(root, run_id)

    outside = tmp_path / "outside_secret.json"
    outside.write_bytes(b'{"secret":true}\n')
    # Replace a pinned allowlisted artifact with a symlink escape.
    link_name = "regime_metrics.json"
    link_path = run_dir / link_name
    assert link_path.is_file()
    link_path.unlink()
    try:
        os.symlink(outside, link_path)
    except OSError as exc:
        pytest.skip(f"symlink not available: {exc}")

    client = _client_for(root)
    try:
        resp = client.get(_content_url(sid, link_name))
        assert resp.status_code != 200
        detail = resp.json()["detail"]
        assert isinstance(detail, dict)
        assert detail["code"] in {
            "not_allowlisted",
            "not_pinned",
            "checksum_mismatch",
            "unsealed_run",
            "not_found",
        }
        assert '{"secret":true}' not in resp.text
        assert str(outside.resolve()) not in resp.text
    finally:
        app.dependency_overrides.pop(get_scorecard_service, None)


def test_directory_instead_of_file(tmp_path: Path) -> None:
    root, _exp, run_id = te._completed_run(tmp_path)
    entry = ExperimentRegistry(root).show(run_id, verify=True)
    run_dir = Path(entry.artifact_path)
    dir_name = "nested_dir.json"
    (run_dir / dir_name).mkdir()

    # Sealing a directory as a checksum key should fail; content GET must not 200.
    checksums = load_checksums(run_dir)
    checksums[dir_name] = hashlib.sha256(b"dir").hexdigest()
    (run_dir / "checksums.json").write_text(
        json.dumps(checksums, sort_keys=True) + "\n", encoding="utf-8"
    )
    with pytest.raises((ValueError, FileNotFoundError, OSError, IsADirectoryError)):
        ExperimentRegistry(root).register_complete(
            experiment_id=entry.experiment_id,
            run_id=run_id,
            attempt_id=entry.attempt_id,
            strategy_version=entry.strategy_version,
            dataset_version=entry.dataset_version,
            cost_model_version=entry.cost_model_version,
            benchmark_ref=entry.benchmark_ref,
            artifact_path=run_dir,
            checksums=checksums,
        )

    sid = _evaluate(root, run_id)
    client = _client_for(root)
    try:
        resp = client.get(_content_url(sid, dir_name))
        assert resp.status_code != 200
        detail = resp.json()["detail"]
        assert detail["code"] in {
            "not_pinned",
            "not_allowlisted",
            "not_found",
            "unsealed_run",
            "checksum_mismatch",
        }
    finally:
        app.dependency_overrides.pop(get_scorecard_service, None)


def test_non_allowlisted_filename(tmp_path: Path) -> None:
    root, _exp, run_id = te._completed_run(tmp_path)
    sid = _evaluate(root, run_id)
    client = _client_for(root)
    try:
        resp = client.get(_content_url(sid, "evil.bin"))
        assert resp.status_code in {400, 404, 415}
        assert resp.json()["detail"]["code"] in {
            "not_pinned",
            "not_allowlisted",
            "unsupported_media_type",
        }
    finally:
        app.dependency_overrides.pop(get_scorecard_service, None)


def test_too_large_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root, _exp, run_id = te._completed_run(tmp_path)
    sid = _evaluate(root, run_id)
    monkeypatch.setattr("research.artifact_content.MAX_ARTIFACT_BYTES", 32)
    client = _client_for(root)
    try:
        resp = client.get(_content_url(sid, "regime_metrics.json"))
        assert resp.status_code == 413
        assert resp.json()["detail"]["code"] == "too_large"
    finally:
        app.dependency_overrides.pop(get_scorecard_service, None)


def test_scorecard_self_path_not_served_as_run_artifact(tmp_path: Path) -> None:
    root, _exp, run_id = te._completed_run(tmp_path)
    record = _evaluator(root).evaluate(run_id=run_id, policy_version="1.0")
    client = _client_for(root)
    try:
        resp = client.get(
            _content_url(record.scorecard_id, f"scorecards/{record.scorecard_id}.json")
        )
        assert resp.status_code in {400, 404}
        assert resp.json()["detail"]["code"] in {"not_allowlisted", "not_pinned"}
    finally:
        app.dependency_overrides.pop(get_scorecard_service, None)


def test_empty_200_never_for_missing_scorecard(tmp_path: Path) -> None:
    root, _exp, run_id = te._completed_run(tmp_path)
    _evaluate(root, run_id)
    client = _client_for(root)
    try:
        resp = client.get(
            _content_url("sc_missing_does_not_exist", "regime_metrics.json")
        )
        assert resp.status_code == 404
        assert resp.content
        assert resp.json()["detail"]["code"] == "not_found"
    finally:
        app.dependency_overrides.pop(get_scorecard_service, None)
