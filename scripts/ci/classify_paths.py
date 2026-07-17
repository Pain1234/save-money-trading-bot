#!/usr/bin/env python3
"""Classify changed file paths to drive the fast/full CI job split.

This script has no third-party dependencies (stdlib only) so it can run in
the very first CI job, before ``pip install`` has happened.

Usage::

    python scripts/ci/classify_paths.py --write-github-output --files-from -
    python scripts/ci/classify_paths.py --write-github-output --base <sha> --head <sha>
    git diff --name-only main... | python scripts/ci/classify_paths.py --write-github-output

The classifier is **fail-closed**: anything it cannot confidently place into a
known, narrow category causes ``run_all_fast`` to be set, which makes the
``ci-fast.yml`` workflow run the full fast-lane test suite instead of a
narrow slice. Docs-only changes are the one case that is fail-open, and only
when *every* changed path is a documentation-style file.
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

# Order matters: this is also the order flags are printed/written in.
FLAG_NAMES: tuple[str, ...] = (
    "docs_only",
    "governance",
    "dependencies",
    "shared_python",
    "research",
    "market_data",
    "paper_trading",
    "backtest",
    "strategy",
    "risk",
    "deploy",
    "database",
    "performance",
    "workflows",
    "run_all_fast",
    "run_quality",
    "run_targeted_tests",
)

# Categories that represent an isolated "service area". If two or more of
# these are touched in the same diff, we fail closed to run_all_fast rather
# than trying to guess which narrow test slices are safe to combine.
_SERVICE_AREA_FLAGS: tuple[str, ...] = (
    "research",
    "market_data",
    "paper_trading",
    "backtest",
    "strategy",
    "risk",
)

_DOC_EXTENSIONS = (".md",)
_DOC_IMAGE_EXTENSIONS = (".png", ".svg", ".jpg", ".jpeg", ".gif", ".webp")

_GOVERNANCE_EXACT_PATHS = frozenset(
    {
        "scripts/github_project_setup.py",
        "ROADMAP.md",
        "AGENTS.md",
        "CHANGELOG.md",
        "docs/PROJECT_OPERATING_SYSTEM.md",
        "docs/DEFINITION_OF_DONE.md",
        "docs/branch-protection.md",
    }
)

_DEPENDENCY_EXACT_PATHS = frozenset(
    {
        "pyproject.toml",
        "package.json",
        "package-lock.json",
        "poetry.lock",
        "setup.cfg",
        "setup.py",
        "uv.lock",
    }
)

_SHARED_PYTHON_EXACT_PATHS = frozenset(
    {
        "tests/conftest.py",
        "tests/postgres_fixtures.py",
    }
)


def normalize_path(path: str) -> str:
    """Normalize a path to forward slashes, no leading ``./``."""
    normalized = path.strip().replace("\\", "/")
    while normalized.startswith("./"):
        normalized = normalized[2:]
    return normalized


def is_docs_only_path(path: str) -> bool:
    """Return True if *path* is a documentation-only candidate.

    Candidates: ``*.md``, ``docs/**``, ``LICENSE*``, ``.gitignore``, image
    files under ``docs/``, and any ``.gitkeep`` marker file.
    """
    path = normalize_path(path)
    if not path:
        return True
    basename = path.rsplit("/", 1)[-1]

    if path.endswith(_DOC_EXTENSIONS):
        return True
    if path == "docs" or path.startswith("docs/"):
        return True
    if basename == "LICENSE" or basename.startswith("LICENSE."):
        return True
    if path == ".gitignore":
        return True
    if basename == ".gitkeep":
        return True
    if path.startswith("docs/") and basename.lower().endswith(_DOC_IMAGE_EXTENSIONS):
        return True
    return False


def _is_governance_path(path: str) -> bool:
    if path in _GOVERNANCE_EXACT_PATHS:
        return True
    if path.startswith("tests/governance/"):
        return True
    if path.startswith(".github/ISSUE_TEMPLATE/"):
        return True
    return False


def _is_dependencies_path(path: str) -> bool:
    if path in _DEPENDENCY_EXACT_PATHS:
        return True
    basename = path.rsplit("/", 1)[-1]
    if basename.startswith("requirements") and basename.endswith(".txt"):
        return True
    if basename.startswith("Pipfile"):
        return True
    return False


def _is_workflows_path(path: str) -> bool:
    return path.startswith(".github/workflows/")


def _is_research_path(path: str) -> bool:
    return (
        path.startswith("services/research/")
        or path.startswith("tests/research/")
        or path.startswith("examples/research/")
    )


def _is_market_data_path(path: str) -> bool:
    return path.startswith("services/market_data/") or path.startswith("tests/market_data/")


def _is_paper_trading_path(path: str) -> bool:
    return path.startswith("services/paper_trading/") or path.startswith("tests/paper_trading/")


def _is_backtest_path(path: str) -> bool:
    return path.startswith("services/backtester/") or path.startswith("tests/backtester/")


def _is_strategy_path(path: str) -> bool:
    return path.startswith("services/strategy_engine/") or path.startswith("tests/strategy_engine/")


def _is_risk_path(path: str) -> bool:
    return (
        path.startswith("services/risk_engine/")
        or path.startswith("tests/risk_engine/")
        or path.startswith("services/trading_constraints/")
        or path.startswith("tests/trading_constraints/")
    )


def _is_deploy_path(path: str) -> bool:
    basename = path.rsplit("/", 1)[-1]
    return (
        path.startswith("deploy/")
        or path.startswith("tests/deploy/")
        or path.startswith("src/")
        or basename.startswith("next.config.")
        or basename.startswith("Dockerfile")
    )


def _is_database_path(path: str) -> bool:
    basename = path.rsplit("/", 1)[-1]
    if path.startswith("alembic/") or "/alembic/" in path:
        return True
    if path.startswith("migrations/") or "/migrations/" in path:
        return True
    if "postgres" in path.lower():
        return True
    if path == "tests/conftest.py":
        return True
    return basename == "alembic.ini"


def _is_performance_path(path: str) -> bool:
    if path.startswith("tests/perf/"):
        return True
    if path.startswith("docs/operations/") and "perf" in path.rsplit("/", 1)[-1].lower():
        return True
    return False


def _is_shared_python_path(path: str) -> bool:
    if path in _SHARED_PYTHON_EXACT_PATHS:
        return True
    if path.startswith("tests/fixtures/"):
        return True
    if path.startswith("tests/e2e/"):
        return True
    if (
        path.startswith("scripts/")
        and path.endswith(".py")
        and path != "scripts/github_project_setup.py"
    ):
        return True
    return False


# Ordered (flag_name, matcher) pairs used both to set flags and to decide
# whether a path is "known" (matches at least one category) for the
# uncertain/fail-closed check. docs_only is handled separately since it is
# an all-paths-must-match rule rather than an any-path-matches rule.
_CATEGORY_MATCHERS: tuple[tuple[str, Callable[[str], bool]], ...] = (
    ("governance", _is_governance_path),
    ("dependencies", _is_dependencies_path),
    ("workflows", _is_workflows_path),
    ("research", _is_research_path),
    ("market_data", _is_market_data_path),
    ("paper_trading", _is_paper_trading_path),
    ("backtest", _is_backtest_path),
    ("strategy", _is_strategy_path),
    ("risk", _is_risk_path),
    ("deploy", _is_deploy_path),
    ("database", _is_database_path),
    ("performance", _is_performance_path),
    ("shared_python", _is_shared_python_path),
)


def _empty_flags(*, run_all_fast: bool, docs_only: bool = False) -> dict[str, bool]:
    flags = dict.fromkeys(FLAG_NAMES, False)
    flags["docs_only"] = docs_only
    flags["run_all_fast"] = run_all_fast
    flags["run_quality"] = not docs_only
    flags["run_targeted_tests"] = not docs_only
    return flags


def classify(paths: list[str]) -> dict[str, bool]:
    """Classify a list of changed file paths into boolean CI routing flags.

    Fail-closed: any unexpected input (empty list, unrecognized path, or an
    internal error) sets ``run_all_fast=True`` so the fast-lane workflow runs
    its full test suite rather than skipping something it should not.
    """
    try:
        return _classify_impl(paths)
    except Exception as exc:  # noqa: BLE001 - deliberately broad, fail-closed
        print(f"classify_paths: classification error, failing closed: {exc}", file=sys.stderr)
        return _empty_flags(run_all_fast=True, docs_only=False)


def _classify_impl(paths: list[str]) -> dict[str, bool]:
    normalized = [normalize_path(p) for p in paths if normalize_path(p)]

    if not normalized:
        return _empty_flags(run_all_fast=True, docs_only=False)

    docs_candidates = [is_docs_only_path(p) for p in normalized]
    docs_only = all(docs_candidates)

    flags = dict.fromkeys(FLAG_NAMES, False)
    flags["docs_only"] = docs_only

    known = [False] * len(normalized)
    for flag_name, matcher in _CATEGORY_MATCHERS:
        matched_any = False
        for idx, path in enumerate(normalized):
            if matcher(path):
                matched_any = True
                known[idx] = True
        if matched_any:
            flags[flag_name] = True

    has_uncertain = any(
        not known[idx] and not docs_candidates[idx] for idx in range(len(normalized))
    )

    multi_service = sum(1 for name in _SERVICE_AREA_FLAGS if flags[name]) >= 2

    flags["run_all_fast"] = not docs_only and (
        flags["dependencies"]
        or flags["workflows"]
        or flags["shared_python"]
        or flags["database"]
        or has_uncertain
        or multi_service
    )
    flags["run_quality"] = (not docs_only) or flags["governance"] or flags["workflows"]
    flags["run_targeted_tests"] = not docs_only

    return flags


def _read_lines(text: str) -> list[str]:
    return [line for line in (raw.strip() for raw in text.splitlines()) if line]


def _git_diff_paths(base: str, head: str) -> list[str]:
    result = subprocess.run(
        ["git", "diff", "--no-color", "--name-only", base, head],
        check=True,
        capture_output=True,
        text=True,
    )
    return _read_lines(result.stdout)


def gather_paths(args: argparse.Namespace) -> list[str]:
    if args.files_from is not None:
        if args.files_from == "-":
            return _read_lines(sys.stdin.read())
        return _read_lines(Path(args.files_from).read_text(encoding="utf-8"))

    if args.base and args.head:
        return _git_diff_paths(args.base, args.head)

    if not sys.stdin.isatty():
        return _read_lines(sys.stdin.read())

    return []


def write_github_output(flags: dict[str, bool]) -> None:
    output_path = os.environ.get("GITHUB_OUTPUT")
    if not output_path:
        print(
            "classify_paths: --write-github-output set but $GITHUB_OUTPUT is not defined; "
            "printing flags to stdout instead",
            file=sys.stderr,
        )
        for name in FLAG_NAMES:
            print(f"{name}={_bool_str(flags[name])}")
        return

    with open(output_path, "a", encoding="utf-8", newline="\n") as fh:
        for name in FLAG_NAMES:
            fh.write(f"{name}={_bool_str(flags[name])}\n")


def write_summary(flags: dict[str, bool], paths: list[str], summary_file: str) -> None:
    lines = ["### CI path classification", "", "| Flag | Value |", "| --- | --- |"]
    for name in FLAG_NAMES:
        lines.append(f"| `{name}` | `{_bool_str(flags[name])}` |")
    lines.append("")
    lines.append(f"<details><summary>{len(paths)} changed file(s)</summary>")
    lines.append("")
    lines.append("```")
    lines.extend(paths if paths else ["(none)"])
    lines.append("```")
    lines.append("</details>")
    lines.append("")

    content = "\n".join(lines)
    with open(summary_file, "a", encoding="utf-8", newline="\n") as fh:
        fh.write(content)


def _bool_str(value: bool) -> str:
    return "true" if value else "false"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Classify changed file paths to drive fast/full CI routing.",
    )
    parser.add_argument(
        "--write-github-output",
        action="store_true",
        help="Append flags to $GITHUB_OUTPUT in key=value form.",
    )
    parser.add_argument(
        "--files-from",
        default=None,
        help="Path to a file with newline-separated changed paths, or '-' for stdin.",
    )
    parser.add_argument("--base", default=None, help="Base git SHA/ref to diff from.")
    parser.add_argument("--head", default=None, help="Head git SHA/ref to diff to.")
    parser.add_argument(
        "--summary-file",
        default=None,
        help="Path to append a markdown classification summary to (e.g. $GITHUB_STEP_SUMMARY).",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        paths = gather_paths(args)
    except Exception as exc:  # noqa: BLE001 - fail-closed on input gathering too
        print(
            f"classify_paths: failed to gather changed paths, failing closed: {exc}",
            file=sys.stderr,
        )
        paths = []
        flags = _empty_flags(run_all_fast=True, docs_only=False)
    else:
        flags = classify(paths)

    print(f"classify_paths: classified {len(paths)} path(s)")
    for name in FLAG_NAMES:
        print(f"  {name}={_bool_str(flags[name])}")

    # Never let an output-writing failure crash the step: a crashed plan job
    # blocks the whole pipeline, which is worse than falling back to running
    # everything. Best-effort write, fail-closed flags already computed above.
    try:
        if args.write_github_output:
            write_github_output(flags)
        if args.summary_file:
            write_summary(flags, paths, args.summary_file)
    except Exception as exc:  # noqa: BLE001 - output writing must not crash CI
        print(f"classify_paths: failed to write outputs: {exc}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
