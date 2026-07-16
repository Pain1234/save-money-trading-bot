"""Contract tests for the fast/full CI workflow split.

These tests read the workflow YAML files as *text* (regex/string checks)
rather than parsing YAML, so they run even when PyYAML is not installed in
the environment executing the test suite. They intentionally focus on the
structural/routing contract described in
docs/ci/ACTIONS_OPTIMIZATION_STAGE_2.md rather than full YAML validation.
"""
from __future__ import annotations

import re
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS_DIR = REPO_ROOT / ".github" / "workflows"

CI_FAST = (WORKFLOWS_DIR / "ci-fast.yml").read_text(encoding="utf-8")
CI_FULL = (WORKFLOWS_DIR / "ci-full.yml").read_text(encoding="utf-8")
CI_LEGACY = (WORKFLOWS_DIR / "ci.yml").read_text(encoding="utf-8")

ALL_WORKFLOW_TEXTS: dict[str, str] = {
    path.name: path.read_text(encoding="utf-8") for path in sorted(WORKFLOWS_DIR.glob("*.yml"))
}


def _job_ids(workflow_text: str) -> list[str]:
    """Extract top-level job ids (2-space-indented keys under jobs:)."""
    match = re.search(r"^jobs:\s*$", workflow_text, flags=re.MULTILINE)
    assert match is not None, "workflow has no top-level 'jobs:' key"
    jobs_section = workflow_text[match.end() :]
    return re.findall(r"^ {2}([A-Za-z0-9_-]+):\s*$", jobs_section, flags=re.MULTILINE)


def _has_job_name(workflow_text: str, name: str) -> bool:
    pattern = rf"name:\s*{re.escape(name)}\s*$"
    return re.search(pattern, workflow_text, flags=re.MULTILINE) is not None


class ConcurrencyTests(unittest.TestCase):
    def test_ci_fast_has_cancel_in_progress_and_fast_group(self) -> None:
        self.assertIn("cancel-in-progress: true", CI_FAST)
        self.assertRegex(CI_FAST, r"group:\s*fast-ci-")

    def test_ci_full_has_full_ci_group(self) -> None:
        self.assertRegex(CI_FULL, r"group:\s*full-ci-")

    def test_fast_and_full_use_different_group_prefixes(self) -> None:
        # Anchored to line-start so this doesn't match the "group:" tail of
        # an unrelated key like "merge_group:".
        fast_group = re.search(r"^\s*group:\s*(\S+)", CI_FAST, flags=re.MULTILINE)
        full_group = re.search(r"^\s*group:\s*(\S+)", CI_FULL, flags=re.MULTILINE)
        self.assertIsNotNone(fast_group)
        self.assertIsNotNone(full_group)
        fast_prefix = fast_group.group(1).split("-${{")[0]
        full_prefix = full_group.group(1).split("-${{")[0]
        self.assertNotEqual(fast_prefix, full_prefix)
        self.assertEqual(fast_prefix, "fast-ci")
        self.assertEqual(full_prefix, "full-ci")


class RunnerAndPermissionsTests(unittest.TestCase):
    def test_no_self_hosted_runners_anywhere(self) -> None:
        for name, text in ALL_WORKFLOW_TEXTS.items():
            with self.subTest(workflow=name):
                self.assertNotIn("self-hosted", text)

    def test_ci_fast_and_ci_full_have_read_only_permissions(self) -> None:
        for text in (CI_FAST, CI_FULL):
            self.assertRegex(text, r"permissions:\s*\n\s*contents:\s*read")
            self.assertRegex(
                text, r"permissions:\s*\n\s*contents:\s*read\s*\n\s*pull-requests:\s*read"
            )

    def test_no_pull_request_target_anywhere(self) -> None:
        for name, text in ALL_WORKFLOW_TEXTS.items():
            with self.subTest(workflow=name):
                self.assertNotIn("pull_request_target", text)

    def test_no_write_all_anywhere(self) -> None:
        for name, text in ALL_WORKFLOW_TEXTS.items():
            with self.subTest(workflow=name):
                self.assertNotIn("write-all", text)


class FullCiExactCommandTests(unittest.TestCase):
    """Full CI must reuse the exact pytest invocations from the old ci.yml."""

    def test_core_unit_test_marker_exact(self) -> None:
        self.assertIn(
            '-m "not postgres and not live and not soak and not reporting"',
            CI_FULL,
        )

    def test_market_data_command_exact(self) -> None:
        self.assertIn(
            'python -m pytest tests/market_data -m "not live and not postgres" -q --tb=short',
            CI_FULL,
        )

    def test_deploy_command_exact(self) -> None:
        self.assertIn("python -m pytest tests/deploy -q --tb=short", CI_FULL)

    def test_postgres_command_exact(self) -> None:
        self.assertIn(
            "python -m pytest tests/paper_trading tests/market_data "
            '-m "postgres and not soak" -q --tb=short',
            CI_FULL,
        )

    def test_reporting_command_exact(self) -> None:
        self.assertIn(
            'python -m pytest tests/perf -m "reporting and postgres" -q --tb=short',
            CI_FULL,
        )

    def test_double_run_repro_command_exact(self) -> None:
        self.assertIn(
            "python -m pytest tests/research/test_double_run_repro.py -v --tb=short",
            CI_FULL,
        )

    def test_load_experiment_spec_command_exact(self) -> None:
        self.assertIn(
            "python -c \"from research.experiment_spec import load_experiment_spec; "
            "load_experiment_spec('examples/research/btc_eth_sol_experiment.example.json', "
            'check_json_schema=True)"',
            CI_FULL,
        )

    def test_research_pytest_paths_exact(self) -> None:
        for fragment in (
            "python -m pytest tests/research \\",
            "tests/paper_trading/test_backtester_parity.py \\",
            "tests/paper_trading/test_backtester_signal_parity.py \\",
        ):
            self.assertIn(fragment, CI_FULL)


class JobNameTests(unittest.TestCase):
    def test_ci_fast_required_job_names_present(self) -> None:
        for name in ("plan", "quality", "targeted-tests", "fast-ci-required"):
            with self.subTest(job=name):
                self.assertTrue(_has_job_name(CI_FAST, name))

    def test_ci_full_required_job_names_present(self) -> None:
        for name in (
            "should-run",
            "full-quality",
            "core-tests",
            "postgres-and-reporting",
            "research-repro",
            "full-ci-required",
        ):
            with self.subTest(job=name):
                self.assertTrue(_has_job_name(CI_FULL, name))

    def test_ci_fast_compatibility_alias_job_names_present(self) -> None:
        for name in ("validate", "requirements-baseline", "lint", "test", "test-market-data"):
            with self.subTest(job=name):
                self.assertTrue(_has_job_name(CI_FAST, name))

    def test_ci_full_compatibility_alias_job_names_present(self) -> None:
        for name in ("test-deploy", "postgres"):
            with self.subTest(job=name):
                self.assertTrue(_has_job_name(CI_FULL, name))


class LegacyWorkflowTests(unittest.TestCase):
    def test_ci_legacy_does_not_trigger_on_pull_request(self) -> None:
        on_match = re.search(r"^on:\s*$", CI_LEGACY, flags=re.MULTILINE)
        self.assertIsNotNone(on_match)
        self.assertIn("workflow_dispatch:", CI_LEGACY)
        self.assertNotIn("pull_request:", CI_LEGACY)
        self.assertNotIn("push:", CI_LEGACY)

    def test_ci_legacy_requires_explicit_confirmation(self) -> None:
        self.assertIn("ROLLBACK-LEGACY-CI", CI_LEGACY)


class FullCiLabelTests(unittest.TestCase):
    def test_full_ci_label_referenced(self) -> None:
        self.assertIn("'full-ci'", CI_FULL)
        self.assertIn("contains(github.event.pull_request.labels.*.name", CI_FULL)


class JobCountConstraintTests(unittest.TestCase):
    def test_ci_fast_job_count_within_phase1_budget(self) -> None:
        job_ids = _job_ids(CI_FAST)
        real_jobs = {"plan", "quality", "targeted-tests", "fast-ci-required"}
        alias_jobs = {"validate", "requirements-baseline", "lint", "test", "test-market-data"}
        self.assertEqual(set(job_ids) & real_jobs, real_jobs)
        self.assertTrue(set(job_ids) - real_jobs <= alias_jobs)
        self.assertLessEqual(len(job_ids), 4 + len(alias_jobs))

    def test_ci_full_job_count_within_phase1_budget(self) -> None:
        job_ids = _job_ids(CI_FULL)
        real_jobs = {
            "should-run",
            "full-quality",
            "core-tests",
            "postgres-and-reporting",
            "research-repro",
            "full-ci-required",
        }
        alias_jobs = {"test-deploy", "postgres"}
        self.assertEqual(set(job_ids) & real_jobs, real_jobs)
        self.assertTrue(set(job_ids) - real_jobs <= alias_jobs)
        self.assertLessEqual(len(job_ids), len(real_jobs) + len(alias_jobs))


class WorkflowRoutingUsesScriptsTests(unittest.TestCase):
    def test_ci_fast_uses_classify_and_gate_scripts(self) -> None:
        self.assertIn("scripts/ci/classify_paths.py", CI_FAST)
        self.assertIn("scripts/ci/check_required_gate.py", CI_FAST)

    def test_ci_full_uses_gate_script(self) -> None:
        self.assertIn("scripts/ci/check_required_gate.py", CI_FULL)


if __name__ == "__main__":
    unittest.main()
