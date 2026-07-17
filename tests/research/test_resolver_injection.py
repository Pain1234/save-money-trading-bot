"""Prove resolved StrategyEngine is what the runner executes (#166)."""

from __future__ import annotations

from pathlib import Path

from research.runner import RunRequest, run_experiment
from research.strategy_resolver import resolve_strategy
from strategy_engine.engine import StrategyEngine

from tests.research.fixtures import REPO_ROOT, align_spec_to_bundle, btc_bundle


class RecordingStrategyEngine(StrategyEngine):
    """Test adapter that records evaluate calls."""

    def __init__(self) -> None:
        super().__init__()
        self.calls = 0

    def evaluate(self, *args, **kwargs):  # noqa: ANN002, ANN003
        self.calls += 1
        return super().evaluate(*args, **kwargs)


def test_runner_uses_resolved_strategy_engine(tmp_path: Path, monkeypatch) -> None:
    bundle = btc_bundle()
    spec = align_spec_to_bundle(tmp_path, bundle)
    recorder = RecordingStrategyEngine()

    def _resolve(s):
        resolved = resolve_strategy(s)
        from research.strategy_resolver import ResolvedStrategy

        return ResolvedStrategy(
            strategy_id=resolved.strategy_id,
            strategy_version=resolved.strategy_version,
            entrypoint=resolved.entrypoint,
            interface_version=resolved.interface_version,
            parameters=resolved.parameters,
            engine=recorder,
        )

    monkeypatch.setattr("research.runner.resolve_strategy", _resolve)
    outcome = run_experiment(
        RunRequest(
            spec=spec,
            bundle=bundle,
            artifacts_root=tmp_path / "out",
            repo_root=REPO_ROOT,
            allow_dirty_git=True,
        )
    )
    assert outcome.status == "complete", outcome.error
    assert recorder.calls > 0
