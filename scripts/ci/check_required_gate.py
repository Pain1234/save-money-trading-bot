#!/usr/bin/env python3
"""Fail-closed gate check for GitHub Actions job results.

Verifies that a set of upstream job results (``needs.<job>.result``) match
the required outcome(s) for each job. A job whose result is missing,
``cancelled``, or outside its allowed set fails the gate.

Simple API (used by the ``*-required`` gate jobs)::

    python scripts/ci/check_required_gate.py \\
        --result plan=success \\
        --result quality=success \\
        --result targeted-tests=skipped \\
        --require plan=success \\
        --require quality=success|skipped \\
        --require targeted-tests=success|skipped

``--need NAME=ALLOWED`` is accepted as an alias for ``--require NAME=ALLOWED``.
``ALLOWED`` may be a single result or a ``|``-separated set, e.g.
``success|skipped``.

Convenience mode (defaults for the fast-lane gate, still overridable)::

    python scripts/ci/check_required_gate.py --mode fast \\
        --result plan=success --result quality=skipped --result targeted-tests=success \\
        --expect-quality false
"""
from __future__ import annotations

import argparse
import sys

# A result is never acceptable for a required job, no matter what the
# configured allowed-set says: GitHub Actions "cancelled" always fails the
# gate for anything actually required.
_NEVER_ALLOWED = frozenset({"cancelled"})

_FAST_MODE_DEFAULTS: dict[str, frozenset[str]] = {
    "plan": frozenset({"success"}),
    "quality": frozenset({"success", "skipped"}),
    "targeted-tests": frozenset({"success", "skipped"}),
}


def parse_allowed(spec: str) -> frozenset[str]:
    """Parse a ``|``-separated allowed-result set, e.g. ``success|skipped``."""
    values = [v.strip() for v in spec.split("|") if v.strip()]
    if not values:
        raise ValueError(f"empty allowed-result set in {spec!r}")
    return frozenset(values)


def _parse_name_value(arg: str, *, sep: str, flag: str) -> tuple[str, str]:
    if sep not in arg:
        raise ValueError(f"{flag} expects NAME{sep}VALUE, got {arg!r}")
    name, _, value = arg.partition(sep)
    name = name.strip()
    value = value.strip()
    if not name or not value:
        raise ValueError(f"{flag} expects NAME{sep}VALUE, got {arg!r}")
    return name, value


def parse_results(specs: list[str]) -> dict[str, str]:
    results: dict[str, str] = {}
    for spec in specs:
        name, value = _parse_name_value(spec, sep="=", flag="--result")
        results[name] = value
    return results


def parse_requirements(
    require_specs: list[str], need_specs: list[str]
) -> dict[str, frozenset[str]]:
    requirements: dict[str, frozenset[str]] = {}
    for spec in require_specs:
        sep = ":" if ":" in spec else "="
        name, value = _parse_name_value(spec, sep=sep, flag="--require")
        requirements[name] = parse_allowed(value)
    for spec in need_specs:
        name, value = _parse_name_value(spec, sep="=", flag="--need")
        requirements[name] = parse_allowed(value)
    return requirements


def apply_mode_defaults(
    requirements: dict[str, frozenset[str]],
    *,
    mode: str | None,
    expect_quality: bool | None,
    expect_targeted_tests: bool | None,
) -> dict[str, frozenset[str]]:
    merged = dict(requirements)
    if mode == "fast":
        for name, allowed in _FAST_MODE_DEFAULTS.items():
            merged.setdefault(name, allowed)

    if expect_quality is True:
        merged["quality"] = frozenset({"success"})
    if expect_targeted_tests is True:
        merged["targeted-tests"] = frozenset({"success"})

    return merged


def evaluate(results: dict[str, str], requirements: dict[str, frozenset[str]]) -> list[str]:
    """Return a list of human-readable failure reasons (empty means pass)."""
    failures: list[str] = []
    for name, allowed in requirements.items():
        if name not in results:
            failures.append(f"required job '{name}' has no reported result")
            continue

        actual = results[name]
        if actual in _NEVER_ALLOWED:
            failures.append(
                f"required job '{name}' was '{actual}', which is never acceptable"
            )
            continue

        if actual not in allowed:
            allowed_str = "|".join(sorted(allowed))
            failures.append(
                f"required job '{name}' result '{actual}' is not in allowed set '{allowed_str}'"
            )

    return failures


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Fail-closed gate check for upstream GitHub Actions job results.",
    )
    parser.add_argument(
        "--result",
        action="append",
        default=[],
        metavar="NAME=RESULT",
        help="Observed result for a job, e.g. plan=success. Repeatable.",
    )
    parser.add_argument(
        "--require",
        action="append",
        default=[],
        metavar="NAME=ALLOWED|ALLOWED2",
        help="Allowed result set for a required job. Repeatable.",
    )
    parser.add_argument(
        "--need",
        action="append",
        default=[],
        metavar="NAME=ALLOWED|ALLOWED2",
        help="Alias for --require.",
    )
    parser.add_argument(
        "--mode",
        choices=["fast"],
        default=None,
        help="Apply default requirements for a known gate mode before overrides.",
    )
    parser.add_argument(
        "--expect-quality",
        choices=["true", "false"],
        default=None,
        help="If true, quality must be success (skipped is treated as unexpected).",
    )
    parser.add_argument(
        "--expect-targeted-tests",
        choices=["true", "false"],
        default=None,
        help="If true, targeted-tests must be success (skipped is treated as unexpected).",
    )
    return parser


def _to_bool(value: str | None) -> bool | None:
    if value is None:
        return None
    return value == "true"


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        results = parse_results(args.result)
        requirements = parse_requirements(args.require, args.need)
    except ValueError as exc:
        print(f"check_required_gate: invalid arguments: {exc}", file=sys.stderr)
        return 1

    requirements = apply_mode_defaults(
        requirements,
        mode=args.mode,
        expect_quality=_to_bool(args.expect_quality),
        expect_targeted_tests=_to_bool(args.expect_targeted_tests),
    )

    if not requirements:
        print("check_required_gate: no requirements configured; nothing to check", file=sys.stderr)
        return 1

    failures = evaluate(results, requirements)

    print("check_required_gate: observed results:")
    for name in sorted(results):
        print(f"  {name}={results[name]}")
    print("check_required_gate: requirements:")
    for name in sorted(requirements):
        print(f"  {name}: {'|'.join(sorted(requirements[name]))}")

    if failures:
        print("check_required_gate: FAILED", file=sys.stderr)
        for reason in failures:
            print(f"  - {reason}", file=sys.stderr)
        return 1

    print("check_required_gate: all required jobs satisfied their allowed result sets")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
