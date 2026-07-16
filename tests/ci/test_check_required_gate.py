"""Tests for scripts/ci/check_required_gate.py."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.ci.check_required_gate import (  # noqa: E402
    apply_mode_defaults,
    evaluate,
    main,
    parse_allowed,
    parse_requirements,
    parse_results,
)


class ParseHelpersTests(unittest.TestCase):
    def test_parse_allowed_single_value(self) -> None:
        self.assertEqual(parse_allowed("success"), frozenset({"success"}))

    def test_parse_allowed_pipe_separated(self) -> None:
        self.assertEqual(parse_allowed("success|skipped"), frozenset({"success", "skipped"}))

    def test_parse_results(self) -> None:
        results = parse_results(["plan=success", "quality=skipped"])
        self.assertEqual(results, {"plan": "success", "quality": "skipped"})

    def test_parse_requirements_equals_separator(self) -> None:
        requirements = parse_requirements(["plan=success", "quality=success|skipped"], [])
        self.assertEqual(requirements["plan"], frozenset({"success"}))
        self.assertEqual(requirements["quality"], frozenset({"success", "skipped"}))

    def test_parse_requirements_colon_separator(self) -> None:
        requirements = parse_requirements(["plan:success|skipped"], [])
        self.assertEqual(requirements["plan"], frozenset({"success", "skipped"}))

    def test_need_is_alias_for_require(self) -> None:
        requirements = parse_requirements([], ["targeted-tests=success|skipped"])
        self.assertEqual(requirements["targeted-tests"], frozenset({"success", "skipped"}))


class EvaluateTests(unittest.TestCase):
    def test_all_satisfied_passes(self) -> None:
        results = {"plan": "success", "quality": "success", "targeted-tests": "skipped"}
        requirements = {
            "plan": frozenset({"success"}),
            "quality": frozenset({"success", "skipped"}),
            "targeted-tests": frozenset({"success", "skipped"}),
        }
        self.assertEqual(evaluate(results, requirements), [])

    def test_missing_required_job_fails(self) -> None:
        results = {"plan": "success"}
        requirements = {"plan": frozenset({"success"}), "quality": frozenset({"success"})}
        failures = evaluate(results, requirements)
        self.assertEqual(len(failures), 1)
        self.assertIn("quality", failures[0])
        self.assertIn("no reported result", failures[0])

    def test_plan_failure_fails(self) -> None:
        results = {"plan": "failure"}
        requirements = {"plan": frozenset({"success"})}
        failures = evaluate(results, requirements)
        self.assertEqual(len(failures), 1)
        self.assertIn("plan", failures[0])

    def test_cancelled_always_fails_even_if_allowed(self) -> None:
        results = {"quality": "cancelled"}
        # Even a permissive allowed set must not accept 'cancelled'.
        requirements = {"quality": frozenset({"success", "skipped", "cancelled"})}
        failures = evaluate(results, requirements)
        self.assertEqual(len(failures), 1)
        self.assertIn("never acceptable", failures[0])

    def test_unexpected_skip_fails_when_only_success_allowed(self) -> None:
        results = {"quality": "skipped"}
        requirements = {"quality": frozenset({"success"})}
        failures = evaluate(results, requirements)
        self.assertEqual(len(failures), 1)

    def test_multiple_failures_all_reported(self) -> None:
        results = {"plan": "failure", "quality": "cancelled"}
        requirements = {
            "plan": frozenset({"success"}),
            "quality": frozenset({"success"}),
            "targeted-tests": frozenset({"success", "skipped"}),
        }
        failures = evaluate(results, requirements)
        self.assertEqual(len(failures), 3)


class ApplyModeDefaultsTests(unittest.TestCase):
    def test_fast_mode_defaults(self) -> None:
        requirements = apply_mode_defaults(
            {}, mode="fast", expect_quality=None, expect_targeted_tests=None
        )
        self.assertEqual(requirements["plan"], frozenset({"success"}))
        self.assertEqual(requirements["quality"], frozenset({"success", "skipped"}))
        self.assertEqual(requirements["targeted-tests"], frozenset({"success", "skipped"}))

    def test_explicit_requirements_override_mode_defaults(self) -> None:
        requirements = apply_mode_defaults(
            {"plan": frozenset({"success", "skipped"})},
            mode="fast",
            expect_quality=None,
            expect_targeted_tests=None,
        )
        # setdefault should not clobber an explicitly provided requirement.
        self.assertEqual(requirements["plan"], frozenset({"success", "skipped"}))

    def test_expect_quality_true_forces_success_only(self) -> None:
        requirements = apply_mode_defaults(
            {"quality": frozenset({"success", "skipped"})},
            mode=None,
            expect_quality=True,
            expect_targeted_tests=None,
        )
        self.assertEqual(requirements["quality"], frozenset({"success"}))

    def test_expect_targeted_tests_true_forces_success_only(self) -> None:
        requirements = apply_mode_defaults(
            {},
            mode=None,
            expect_quality=None,
            expect_targeted_tests=True,
        )
        self.assertEqual(requirements["targeted-tests"], frozenset({"success"}))


class MainCliTests(unittest.TestCase):
    def test_main_exits_zero_on_success(self) -> None:
        exit_code = main(
            [
                "--result",
                "plan=success",
                "--result",
                "quality=success",
                "--result",
                "targeted-tests=skipped",
                "--require",
                "plan=success",
                "--require",
                "quality=success|skipped",
                "--require",
                "targeted-tests=success|skipped",
            ]
        )
        self.assertEqual(exit_code, 0)

    def test_main_exits_one_on_failure(self) -> None:
        exit_code = main(
            [
                "--result",
                "plan=failure",
                "--require",
                "plan=success",
            ]
        )
        self.assertEqual(exit_code, 1)

    def test_main_exits_one_on_unexpected_skip(self) -> None:
        exit_code = main(
            [
                "--result",
                "plan=success",
                "--result",
                "quality=skipped",
                "--require",
                "plan=success",
                "--require",
                "quality=success",
            ]
        )
        self.assertEqual(exit_code, 1)

    def test_main_with_need_alias(self) -> None:
        exit_code = main(
            [
                "--result",
                "plan=success",
                "--need",
                "plan=success",
            ]
        )
        self.assertEqual(exit_code, 0)

    def test_main_fails_when_required_job_missing_entirely(self) -> None:
        exit_code = main(
            [
                "--result",
                "plan=success",
                "--require",
                "plan=success",
                "--require",
                "quality=success",
            ]
        )
        self.assertEqual(exit_code, 1)

    def test_main_exits_one_when_no_requirements_configured(self) -> None:
        exit_code = main(["--result", "plan=success"])
        self.assertEqual(exit_code, 1)

    def test_main_fast_mode_default(self) -> None:
        exit_code = main(
            [
                "--mode",
                "fast",
                "--result",
                "plan=success",
                "--result",
                "quality=skipped",
                "--result",
                "targeted-tests=success",
            ]
        )
        self.assertEqual(exit_code, 0)

    def test_main_invalid_argument_format_fails(self) -> None:
        exit_code = main(["--result", "plan_success_no_equals"])
        self.assertEqual(exit_code, 1)


if __name__ == "__main__":
    unittest.main()
