"""CLI: python -m research validate|run|inspect|list|show|compare|invalidate."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from backtester.models import HistoricalDataBundle

from research.artifacts import load_checksums
from research.costs import COST_MODEL_VERSION
from research.experiment_spec import load_experiment_spec
from research.registry import ExperimentRegistry
from research.runner import RunRequest, inspect_run, run_experiment, validate_spec_path


def _cost_model_version_from_artifacts(artifact_path: Path) -> str:
    """Prefer costs.json pin; fall back to COST_MODEL_VERSION."""
    costs_path = artifact_path / "costs.json"
    if costs_path.is_file():
        raw = json.loads(costs_path.read_text(encoding="utf-8"))
        version = raw.get("cost_model_version")
        if isinstance(version, str) and version.strip():
            return version.strip()
    return COST_MODEL_VERSION


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _load_bundle(path: Path) -> HistoricalDataBundle:
    raw = json.loads(path.read_text(encoding="utf-8"))
    return HistoricalDataBundle.model_validate(raw)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m research")
    sub = parser.add_subparsers(dest="command", required=True)

    p_val = sub.add_parser("validate", help="Validate an ExperimentSpec")
    p_val.add_argument("spec")

    p_run = sub.add_parser("run", help="Run an experiment")
    p_run.add_argument("spec")
    p_run.add_argument("--bundle", required=True, help="HistoricalDataBundle JSON")
    p_run.add_argument("--artifacts-root", default=".")
    p_run.add_argument("--dry-run", action="store_true")

    p_ins = sub.add_parser("inspect", help="Inspect a completed run directory")
    p_ins.add_argument("run_dir")

    p_list = sub.add_parser("list", help="List registry entries")
    p_list.add_argument("--artifacts-root", default=".")

    p_show = sub.add_parser("show", help="Show a run_id from registry")
    p_show.add_argument("run_id")
    p_show.add_argument("--artifacts-root", default=".")

    p_cmp = sub.add_parser("compare", help="Compare two run_ids")
    p_cmp.add_argument("run_a")
    p_cmp.add_argument("run_b")
    p_cmp.add_argument("--artifacts-root", default=".")

    p_inv = sub.add_parser("invalidate", help="Invalidate a run via sidecar")
    p_inv.add_argument("run_id")
    p_inv.add_argument("--reason", required=True)
    p_inv.add_argument("--actor", default="cli")
    p_inv.add_argument("--replacement-run-id")
    p_inv.add_argument("--artifacts-root", default=".")

    args = parser.parse_args(argv)
    root = _repo_root()

    if args.command == "validate":
        spec = validate_spec_path(Path(args.spec))
        print(json.dumps({"ok": True, "strategy_version": spec.strategy_version}))
        return 0

    if args.command == "run":
        spec = load_experiment_spec(args.spec, check_json_schema=True)
        bundle = _load_bundle(Path(args.bundle))
        outcome = run_experiment(
            RunRequest(
                spec=spec,
                bundle=bundle,
                artifacts_root=Path(args.artifacts_root),
                repo_root=root,
                dry_run=args.dry_run,
            )
        )
        print(json.dumps(outcome.__dict__, default=str))
        if outcome.status == "complete" and outcome.artifact_path is not None:
            registry = ExperimentRegistry(Path(args.artifacts_root))
            registry.register_complete(
                experiment_id=outcome.experiment_id,
                run_id=outcome.run_id,
                attempt_id=outcome.attempt_id,
                strategy_version=spec.strategy_version,
                dataset_version=spec.dataset_manifest_ref.dataset_id,
                cost_model_version=_cost_model_version_from_artifacts(
                    outcome.artifact_path
                ),
                benchmark_ref=spec.benchmark,
                artifact_path=outcome.artifact_path,
                checksums=load_checksums(outcome.artifact_path),
            )
        return 0 if outcome.status in {"complete", "dry_run"} else 1

    if args.command == "inspect":
        print(json.dumps(inspect_run(Path(args.run_dir)), default=str, indent=2))
        return 0

    registry = ExperimentRegistry(Path(args.artifacts_root))
    if args.command == "list":
        rows = [e.__dict__ for e in registry.list_entries()]
        print(json.dumps(rows, default=str, indent=2))
        return 0
    if args.command == "show":
        print(json.dumps(registry.show(args.run_id).__dict__, default=str, indent=2))
        return 0
    if args.command == "compare":
        result = registry.compare(args.run_a, args.run_b)
        # dataclasses in result — convert
        result["a"] = result["a"].__dict__
        result["b"] = result["b"].__dict__
        print(json.dumps(result, default=str, indent=2))
        return 0 if result["compatible"] else 2
    if args.command == "invalidate":
        path = registry.invalidate(
            args.run_id,
            reason=args.reason,
            actor=args.actor,
            replacement_run_id=args.replacement_run_id,
        )
        print(json.dumps({"ok": True, "sidecar": str(path)}))
        return 0

    return 1


if __name__ == "__main__":
    sys.exit(main())
