"""Tests for scripts/ci/classify_paths.py.

Covers the fast/full CI routing contract: docs-only detection, each named
service area, dependency/workflow/governance/database triggers, the
shared-python fail-closed triggers, multi-service fan-out, unknown/uncertain
paths, and the empty-diff fail-closed default.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.ci.classify_paths import classify, is_docs_only_path  # noqa: E402


def _all_false_except(flags: dict[str, bool], *true_names: str) -> bool:
    """Helper: assert every flag not in *true_names* is False."""
    return all(flags[name] is False for name in flags if name not in true_names)


class IsDocsOnlyPathTests(unittest.TestCase):
    def test_markdown_file_is_docs_only(self) -> None:
        self.assertTrue(is_docs_only_path("README.md"))
        self.assertTrue(is_docs_only_path("ROADMAP.md"))

    def test_docs_directory_is_docs_only(self) -> None:
        self.assertTrue(is_docs_only_path("docs/ARCHITECTURE.md"))
        self.assertTrue(is_docs_only_path("docs/operations/notes.txt"))

    def test_license_variants_are_docs_only(self) -> None:
        self.assertTrue(is_docs_only_path("LICENSE"))
        self.assertTrue(is_docs_only_path("LICENSE.md"))
        self.assertTrue(is_docs_only_path("LICENSE.txt"))

    def test_gitignore_is_docs_only(self) -> None:
        self.assertTrue(is_docs_only_path(".gitignore"))

    def test_gitkeep_anywhere_is_docs_only(self) -> None:
        self.assertTrue(is_docs_only_path(".gitkeep"))
        self.assertTrue(is_docs_only_path("services/research/.gitkeep"))

    def test_docs_images_are_docs_only(self) -> None:
        self.assertTrue(is_docs_only_path("docs/diagrams/flow.png"))
        self.assertTrue(is_docs_only_path("docs/diagrams/flow.svg"))

    def test_python_source_is_not_docs_only(self) -> None:
        self.assertFalse(is_docs_only_path("services/research/runner.py"))

    def test_backslash_path_is_normalized(self) -> None:
        self.assertTrue(is_docs_only_path("docs\\ARCHITECTURE.md"))


class ClassifyDocsOnlyTests(unittest.TestCase):
    def test_single_markdown_file_is_docs_only(self) -> None:
        flags = classify(["docs/ARCHITECTURE.md"])
        self.assertTrue(flags["docs_only"])
        self.assertFalse(flags["run_all_fast"])
        self.assertFalse(flags["run_quality"])
        self.assertFalse(flags["run_targeted_tests"])

    def test_multiple_docs_files_are_docs_only(self) -> None:
        flags = classify(["README.md", "docs/ARCHITECTURE.md", "LICENSE"])
        self.assertTrue(flags["docs_only"])
        self.assertFalse(flags["run_all_fast"])

    def test_docs_plus_code_file_is_not_docs_only(self) -> None:
        flags = classify(["README.md", "services/research/runner.py"])
        self.assertFalse(flags["docs_only"])
        self.assertTrue(flags["research"])

    def test_governance_flagged_markdown_is_docs_only_and_governance(self) -> None:
        flags = classify(["docs/branch-protection.md"])
        self.assertTrue(flags["docs_only"])
        self.assertTrue(flags["governance"])
        # Governance-flagged docs still get lightweight quality checks.
        self.assertTrue(flags["run_quality"])
        self.assertFalse(flags["run_targeted_tests"])
        self.assertFalse(flags["run_all_fast"])


class ClassifyGovernanceTests(unittest.TestCase):
    def test_roadmap_change_is_governance(self) -> None:
        flags = classify(["ROADMAP.md"])
        self.assertTrue(flags["governance"])

    def test_issue_template_change_is_governance(self) -> None:
        flags = classify([".github/ISSUE_TEMPLATE/bug.yml"])
        self.assertTrue(flags["governance"])
        self.assertFalse(flags["docs_only"])
        self.assertTrue(flags["run_quality"])

    def test_governance_test_directory_is_governance(self) -> None:
        flags = classify(["tests/governance/test_github_project_setup.py"])
        self.assertTrue(flags["governance"])
        self.assertFalse(flags["run_all_fast"])

    def test_github_project_setup_script_is_governance_not_shared(self) -> None:
        flags = classify(["scripts/github_project_setup.py"])
        self.assertTrue(flags["governance"])
        self.assertFalse(flags["shared_python"])
        self.assertFalse(flags["run_all_fast"])


class ClassifyDependenciesTests(unittest.TestCase):
    def test_pyproject_change_triggers_dependencies_and_run_all_fast(self) -> None:
        flags = classify(["pyproject.toml"])
        self.assertTrue(flags["dependencies"])
        self.assertTrue(flags["run_all_fast"])
        self.assertFalse(flags["docs_only"])

    def test_requirements_baseline_triggers_dependencies(self) -> None:
        flags = classify(["requirements-baseline.txt"])
        self.assertTrue(flags["dependencies"])
        self.assertTrue(flags["run_all_fast"])

    def test_package_lock_triggers_dependencies(self) -> None:
        flags = classify(["package-lock.json"])
        self.assertTrue(flags["dependencies"])
        self.assertTrue(flags["run_all_fast"])


class ClassifyWorkflowsTests(unittest.TestCase):
    def test_workflow_change_triggers_workflows_and_run_all_fast(self) -> None:
        flags = classify([".github/workflows/ci-fast.yml"])
        self.assertTrue(flags["workflows"])
        self.assertTrue(flags["run_all_fast"])
        self.assertTrue(flags["run_quality"])
        self.assertTrue(flags["run_targeted_tests"])


class ClassifyServiceAreaTests(unittest.TestCase):
    def test_research_only_change(self) -> None:
        flags = classify(["services/research/runner.py", "tests/research/test_runner.py"])
        self.assertTrue(flags["research"])
        self.assertFalse(flags["run_all_fast"])
        self.assertTrue(flags["run_quality"])
        self.assertTrue(flags["run_targeted_tests"])
        self.assertFalse(flags["market_data"])
        self.assertFalse(flags["paper_trading"])

    def test_market_data_only_change(self) -> None:
        flags = classify(["services/market_data/hyperliquid/client.py"])
        self.assertTrue(flags["market_data"])
        self.assertFalse(flags["run_all_fast"])
        self.assertFalse(flags["research"])

    def test_paper_trading_only_change(self) -> None:
        flags = classify(["tests/paper_trading/test_ledger.py"])
        self.assertTrue(flags["paper_trading"])
        self.assertFalse(flags["run_all_fast"])

    def test_backtest_only_change(self) -> None:
        flags = classify(["services/backtester/engine.py"])
        self.assertTrue(flags["backtest"])
        self.assertFalse(flags["run_all_fast"])

    def test_strategy_only_change(self) -> None:
        flags = classify(["services/strategy_engine/signals.py"])
        self.assertTrue(flags["strategy"])
        self.assertFalse(flags["run_all_fast"])

    def test_risk_only_change(self) -> None:
        flags = classify(["services/risk_engine/limits.py"])
        self.assertTrue(flags["risk"])
        self.assertFalse(flags["run_all_fast"])

    def test_trading_constraints_maps_to_risk(self) -> None:
        flags = classify(["services/trading_constraints/rules.py"])
        self.assertTrue(flags["risk"])
        self.assertFalse(flags["run_all_fast"])

    def test_deploy_only_change(self) -> None:
        flags = classify(["src/app/page.tsx", "next.config.ts"])
        self.assertTrue(flags["deploy"])
        self.assertFalse(flags["run_all_fast"])

    def test_dockerfile_change_is_deploy(self) -> None:
        flags = classify(["deploy/Dockerfile.paper-python"])
        self.assertTrue(flags["deploy"])


class ClassifyDatabaseTests(unittest.TestCase):
    def test_alembic_migration_triggers_database_and_run_all_fast(self) -> None:
        flags = classify(["migrations/versions/0001_init.py"])
        self.assertTrue(flags["database"])
        self.assertTrue(flags["run_all_fast"])

    def test_postgres_named_file_triggers_database(self) -> None:
        flags = classify(["tests/postgres_fixtures.py"])
        self.assertTrue(flags["database"])
        self.assertTrue(flags["shared_python"])
        self.assertTrue(flags["run_all_fast"])

    def test_conftest_triggers_database_and_shared_python(self) -> None:
        flags = classify(["tests/conftest.py"])
        self.assertTrue(flags["database"])
        self.assertTrue(flags["shared_python"])
        self.assertTrue(flags["run_all_fast"])


class ClassifyAgentLoopAndPerformanceTests(unittest.TestCase):
    def test_agent_loop_directory_change(self) -> None:
        flags = classify([".agent-loop/config.yml"])
        self.assertTrue(flags["agent_loop"])
        self.assertFalse(flags["run_all_fast"])

    def test_perf_test_change(self) -> None:
        flags = classify(["tests/perf/test_dashboard_api_baseline.py"])
        self.assertTrue(flags["performance"])
        self.assertFalse(flags["run_all_fast"])

    def test_perf_docs_change(self) -> None:
        flags = classify(["docs/operations/dashboard-perf-regression.md"])
        # Doc file under docs/ -> docs_only candidate too.
        self.assertTrue(flags["performance"])
        self.assertTrue(flags["docs_only"])


class ClassifySharedPythonTests(unittest.TestCase):
    def test_tests_fixtures_triggers_shared_python_fail_closed(self) -> None:
        flags = classify(["tests/fixtures/perf/sample.json"])
        self.assertTrue(flags["shared_python"])
        self.assertTrue(flags["run_all_fast"])

    def test_tests_e2e_triggers_shared_python_fail_closed(self) -> None:
        flags = classify(["tests/e2e/dashboard-routes.spec.ts"])
        self.assertTrue(flags["shared_python"])
        self.assertTrue(flags["run_all_fast"])

    def test_generic_script_triggers_shared_python(self) -> None:
        flags = classify(["scripts/reconcile_accounting.py"])
        self.assertTrue(flags["shared_python"])
        self.assertTrue(flags["run_all_fast"])


class ClassifyMultiServiceTests(unittest.TestCase):
    def test_two_service_areas_trigger_run_all_fast(self) -> None:
        flags = classify(
            [
                "services/strategy_engine/signals.py",
                "services/paper_trading/executor.py",
            ]
        )
        self.assertTrue(flags["strategy"])
        self.assertTrue(flags["paper_trading"])
        self.assertTrue(flags["run_all_fast"])

    def test_three_service_areas_trigger_run_all_fast(self) -> None:
        flags = classify(
            [
                "services/research/runner.py",
                "services/market_data/client.py",
                "services/backtester/engine.py",
            ]
        )
        self.assertTrue(flags["run_all_fast"])

    def test_single_service_area_does_not_trigger_multi_service(self) -> None:
        flags = classify(
            [
                "services/research/runner.py",
                "services/research/other.py",
                "tests/research/test_runner.py",
            ]
        )
        self.assertFalse(flags["run_all_fast"])


class ClassifyUncertainPathTests(unittest.TestCase):
    def test_unknown_root_file_triggers_run_all_fast(self) -> None:
        flags = classify(["some_new_top_level_thing.xyz"])
        self.assertTrue(flags["run_all_fast"])
        self.assertFalse(flags["docs_only"])

    def test_dotfile_directory_triggers_run_all_fast(self) -> None:
        flags = classify([".cursor/settings.json"])
        self.assertTrue(flags["run_all_fast"])

    def test_known_file_mixed_with_unknown_file_triggers_run_all_fast(self) -> None:
        flags = classify(["services/research/runner.py", "random/unmapped/file.bin"])
        self.assertTrue(flags["research"])
        self.assertTrue(flags["run_all_fast"])


class ClassifyEmptyAndErrorTests(unittest.TestCase):
    def test_empty_list_triggers_run_all_fast(self) -> None:
        flags = classify([])
        self.assertTrue(flags["run_all_fast"])
        self.assertFalse(flags["docs_only"])
        self.assertTrue(flags["run_quality"])
        self.assertTrue(flags["run_targeted_tests"])

    def test_blank_strings_are_ignored_and_treated_as_empty(self) -> None:
        flags = classify(["", "   ", "\n"])
        self.assertTrue(flags["run_all_fast"])

    def test_classify_never_raises_on_bad_input(self) -> None:
        # None is not a valid path; classify() must fail closed, not raise.
        flags = classify([None])  # type: ignore[list-item]
        self.assertTrue(flags["run_all_fast"])


class ClassifyOutputContractTests(unittest.TestCase):
    def test_all_flags_present_and_boolean(self) -> None:
        flags = classify(["services/research/runner.py"])
        expected_keys = {
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
            "agent_loop",
            "performance",
            "workflows",
            "run_all_fast",
            "run_quality",
            "run_targeted_tests",
        }
        self.assertEqual(set(flags.keys()), expected_keys)
        for value in flags.values():
            self.assertIsInstance(value, bool)


if __name__ == "__main__":
    unittest.main()
