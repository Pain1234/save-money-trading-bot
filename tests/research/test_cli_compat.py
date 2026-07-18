"""CLI compatibility smoke for Issue #250 (P4.8).

The Research Workspace UI/API must never replace or break the existing
``python -m research`` CLI (Lab and CLI share the same runner/registry).
Deep CLI behavior is already covered elsewhere (``test_runner_registry.py``,
``test_compare_semantics.py``, ``test_double_run_repro.py``); this module is
a lightweight regression guard that the CLI entry point, its ``compare``
subcommand, and the ``research.repro`` module used for double-run checks
stay importable and wired up.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def _cli_env() -> dict[str, str]:
    """`python -m research` needs `services/` on PYTHONPATH (see pyproject.toml
    `[tool.pytest.ini_options] pythonpath`, which only applies inside the
    pytest process, not to subprocesses spawned from it)."""
    env = dict(os.environ)
    services = str(REPO_ROOT / "services")
    existing = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = (
        services if not existing else services + os.pathsep + existing
    )
    return env


def test_research_module_importable() -> None:
    import research.__main__ as cli_main
    import research.repro as repro

    assert callable(cli_main.main)
    assert callable(repro.compare_semantic_run_dirs)
    assert callable(repro.semantic_manifest_from_file)


def test_cli_help_lists_compare_and_core_subcommands() -> None:
    proc = subprocess.run(
        [sys.executable, "-m", "research", "-h"],
        check=True,
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
        env=_cli_env(),
    )
    out = proc.stdout + proc.stderr
    for command in ("validate", "run", "inspect", "list", "show", "compare", "invalidate"):
        assert command in out, f"CLI help missing {command!r} subcommand"


def test_cli_compare_missing_args_fails_fast_without_crash() -> None:
    """`compare` requires two run ids; wrong usage must exit non-zero, not crash."""
    proc = subprocess.run(
        [sys.executable, "-m", "research", "compare"],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
        env=_cli_env(),
    )
    assert proc.returncode != 0
    assert "usage" in (proc.stdout + proc.stderr).lower()


def test_cli_compare_round_trip(tmp_path: Path) -> None:
    """Two identical runs registered via the CLI stay comparable end-to-end."""
    from research.artifacts import load_checksums
    from research.registry import ExperimentRegistry
    from research.runner import RunRequest, run_experiment

    from tests.research.fixtures import align_spec_to_bundle, btc_bundle

    bundle = btc_bundle()
    spec = align_spec_to_bundle(tmp_path, bundle)
    artifacts_root = tmp_path / "artifacts_root"

    outcome = run_experiment(
        RunRequest(
            spec=spec,
            bundle=bundle,
            artifacts_root=artifacts_root,
            repo_root=REPO_ROOT,
            allow_dirty_git=True,
        )
    )
    assert outcome.status == "complete", outcome.error
    assert outcome.artifact_path is not None

    registry = ExperimentRegistry(artifacts_root)
    registry.register_complete(
        experiment_id=outcome.experiment_id,
        run_id=outcome.run_id,
        attempt_id=outcome.attempt_id,
        strategy_version=spec.strategy_version,
        dataset_version=spec.dataset_manifest_ref.dataset_id,
        cost_model_version="1.1",
        benchmark_ref=spec.benchmark,
        artifact_path=outcome.artifact_path,
        checksums=load_checksums(outcome.artifact_path),
    )

    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "research",
            "compare",
            outcome.run_id,
            outcome.run_id,
            "--artifacts-root",
            str(artifacts_root),
        ],
        check=True,
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
        env=_cli_env(),
    )
    assert '"compatible": true' in proc.stdout
