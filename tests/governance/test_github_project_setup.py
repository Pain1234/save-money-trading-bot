"""Unit tests for the idempotent GitHub governance setup script."""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

SCRIPTS_DIR = Path(__file__).resolve().parents[2] / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import github_project_setup as setup

APPROVED_REPO = setup.DUPLICATE_REPAIR_REPOSITORY
FOREIGN_REPO = "owner/repository"


def gh_result(
    stdout: str = "",
    stderr: str = "",
    returncode: int = 0,
) -> MagicMock:
    return MagicMock(stdout=stdout, stderr=stderr, returncode=returncode)


def is_mutating_gh_command(args: list[str]) -> bool:
    if len(args) < 2:
        return False
    if args[:2] in (["issue", "comment"], ["issue", "close"], ["issue", "edit"], ["issue", "create"]):
        return True
    if args[:2] == ["label", "create"]:
        return True
    if args[0] == "project":
        return True
    if args[0] == "api" and len(args) > 1 and "milestones" in args[1] and "-f" in args:
        return True
    return False


def issue_payload(
    number: int,
    title: str,
    *,
    state: str = "OPEN",
) -> str:
    return json.dumps({"number": number, "state": state, "title": title, "body": ""})


class GitHubProjectSetupTests(unittest.TestCase):
    def setUp(self) -> None:
        self.context = setup.GhContext(
            available=True,
            authenticated=True,
            repo=FOREIGN_REPO,
            dry_run=False,
        )
        self.approved_context = setup.GhContext(
            available=True,
            authenticated=True,
            repo=APPROVED_REPO,
            dry_run=False,
        )
        self.seed_issue = setup.SeedIssue(
            "test-governance-seed",
            f"{chr(0x00DC)}berpr{chr(0x00FC)}fung {chr(0x2013)} Seed Issue",
            "P0 – Governance and Scope Freeze",
            ("area:governance",),
            "Seed body",
        )
        self.sample_repair = setup.DuplicateRepair(
            duplicate_number=17,
            canonical_number=2,
            expected_title="Repository-Governance einführen",
            seed_key="p0-repository-governance",
        )

    def test_normalize_title_handles_dash_spaces_case_umlauts_and_mojibake(self) -> None:
        umlaut_title = f"P0 {chr(0x2013)} {chr(0x00DC)}berpr{chr(0x00FC)}fung"
        expected = f"p0 - {chr(0x00FC)}berpr{chr(0x00FC)}fung"
        variants = (
            umlaut_title,
            f" p0  {chr(0x2014)}  {umlaut_title.upper().split(' ', 2)[2]} ",
            umlaut_title.replace(chr(0x2013), "-"),
            umlaut_title.encode("utf-8").decode("latin1"),
        )

        self.assertEqual([setup.normalize_title(value) for value in variants], [expected] * 4)

    def test_open_issue_with_marker_is_detected_by_title(self) -> None:
        issue = {"title": self.seed_issue.title, "body": setup.seed_key_marker(self.seed_issue.key)}
        with patch.object(setup, "SEED_ISSUES", [self.seed_issue]), patch.object(
            setup, "run_gh", return_value=gh_result(stdout=json.dumps([issue]))
        ):
            setup.ensure_seed_issues(self.context, {self.seed_issue.milestone: 1})

        self.assertFalse(self.context.warnings)

    def test_closed_issue_with_marker_is_detected_by_title(self) -> None:
        issue = {
            "title": self.seed_issue.title,
            "body": setup.seed_key_marker(self.seed_issue.key),
            "state": "CLOSED",
        }
        with patch.object(setup, "SEED_ISSUES", [self.seed_issue]), patch.object(
            setup, "run_gh", return_value=gh_result(stdout=json.dumps([issue]))
        ) as runner:
            setup.ensure_seed_issues(self.context, {self.seed_issue.milestone: 1})

        self.assertEqual(runner.call_count, 1)

    def test_title_without_marker_is_detected(self) -> None:
        issue = {"title": self.seed_issue.title, "body": "Created before markers were introduced."}
        with patch.object(setup, "SEED_ISSUES", [self.seed_issue]), patch.object(
            setup, "run_gh", return_value=gh_result(stdout=json.dumps([issue]))
        ) as runner:
            setup.ensure_seed_issues(self.context, {self.seed_issue.milestone: 1})

        self.assertEqual(runner.call_count, 1)

    def test_wrong_title_with_marker_is_detected_by_seed_key(self) -> None:
        issue = {"title": "Different issue", "body": setup.seed_key_marker(self.seed_issue.key)}
        runner = MagicMock(return_value=gh_result(stdout=json.dumps([issue])))
        with patch.object(setup, "SEED_ISSUES", [self.seed_issue]), patch.object(
            setup, "run_gh", runner
        ):
            setup.ensure_seed_issues(self.context, {self.seed_issue.milestone: 1})

        self.assertEqual(runner.call_count, 1)

    def test_sequential_apply_creates_seed_only_once(self) -> None:
        existing_issues: list[dict[str, str]] = []
        create_calls: list[list[str]] = []

        def run_gh(args: list[str], **_kwargs: object) -> MagicMock:
            if args[0] == "api" and "/issues?" in args[1]:
                return gh_result(stdout=json.dumps(existing_issues))
            if args[:2] == ["issue", "create"]:
                create_calls.append(args)
                existing_issues.append(
                    {
                        "title": args[args.index("--title") + 1],
                        "body": args[args.index("--body") + 1],
                    }
                )
                return gh_result(stdout="https://github.com/owner/repository/issues/1")
            self.fail(f"Unexpected gh invocation: {args}")

        with patch.object(setup, "SEED_ISSUES", [self.seed_issue]), patch.object(
            setup, "run_gh", side_effect=run_gh
        ):
            setup.ensure_seed_issues(self.context, {self.seed_issue.milestone: 1})
            first_apply_creates = len(create_calls)
            setup.ensure_seed_issues(self.context, {self.seed_issue.milestone: 1})

        self.assertEqual(first_apply_creates, 1)
        self.assertEqual(len(create_calls), 1)

    def test_refresh_before_create_skips_concurrently_created_seed(self) -> None:
        concurrent_issue = {
            "number": 99,
            "title": self.seed_issue.title,
            "body": setup.with_seed_body(self.seed_issue),
        }
        runner = MagicMock(
            side_effect=[
                gh_result(stdout="[]"),
                gh_result(stdout=json.dumps([concurrent_issue])),
            ]
        )
        with patch.object(setup, "SEED_ISSUES", [self.seed_issue]), patch.object(
            setup, "run_gh", runner
        ):
            setup.ensure_seed_issues(self.context, {self.seed_issue.milestone: 1})

        self.assertEqual(runner.call_count, 2)

    def test_local_milestone_state_prevents_duplicate_phase_create_in_same_run(self) -> None:
        milestones = [
            ("P0 – First governance milestone", "first"),
            ("P0 – Duplicate phase milestone", "duplicate"),
        ]
        runner = MagicMock(
            side_effect=[
                gh_result(stdout="[]"),
                gh_result(stdout=json.dumps({"number": 7})),
                gh_result(stdout=json.dumps([{"title": milestones[0][0], "number": 7}])),
            ]
        )
        with patch.object(setup, "MILESTONES", milestones), patch.object(setup, "run_gh", runner):
            setup.ensure_milestones(self.context)

        create_calls = [
            call
            for call in runner.call_args_list
            if call.args[0][:2] == ["api", "repos/owner/repository/milestones"]
            and "-f" in call.args[0]
        ]
        self.assertEqual(len(create_calls), 1)

    def test_api_failure_warns_and_does_not_create_labels(self) -> None:
        runner = MagicMock(return_value=gh_result(stderr="forbidden", returncode=1))
        with patch.object(setup, "LABELS", [("area:test", "123456", "test")]), patch.object(
            setup, "run_gh", runner
        ):
            setup.ensure_labels(self.context)

        self.assertIn("could not list labels: forbidden", self.context.warnings)
        self.assertIn("label create failed for 'area:test': forbidden", self.context.warnings)
        self.assertEqual(runner.call_count, 2)

    def test_bad_milestone_json_warns_and_returns_empty_map(self) -> None:
        with patch.object(setup, "run_gh", return_value=gh_result(stdout="not json")):
            result = setup.ensure_milestones(self.context)

        self.assertEqual(result, {})
        self.assertIn("could not parse milestones JSON", self.context.warnings)

    def test_no_authentication_skips_github_calls(self) -> None:
        unauthenticated = setup.GhContext(True, False, FOREIGN_REPO, False)
        runner = MagicMock()
        with patch.object(setup, "SEED_ISSUES", [self.seed_issue]), patch.object(
            setup, "run_gh", runner
        ):
            setup.ensure_labels(unauthenticated)
            setup.ensure_milestones(unauthenticated)
            setup.ensure_seed_issues(unauthenticated, {self.seed_issue.milestone: 1})

        self.assertFalse(runner.called)

    def test_missing_milestone_creates_issue_without_milestone_argument(self) -> None:
        runner = MagicMock(
            side_effect=[
                gh_result(stdout="[]"),
                gh_result(stdout="[]"),
                gh_result(stdout="https://github.com/owner/repository/issues/1"),
            ]
        )
        with patch.object(setup, "SEED_ISSUES", [self.seed_issue]), patch.object(
            setup, "run_gh", runner
        ):
            setup.ensure_seed_issues(self.context, {})
        create_args = runner.call_args.args[0]

        self.assertNotIn("--milestone", create_args)

    def test_issue_create_failure_is_recorded_as_warning(self) -> None:
        runner = MagicMock(
            side_effect=[
                gh_result(stdout="[]"),
                gh_result(stdout="[]"),
                gh_result(stderr="validation failed", returncode=1),
            ]
        )
        with patch.object(setup, "SEED_ISSUES", [self.seed_issue]), patch.object(
            setup, "run_gh", runner
        ):
            setup.ensure_seed_issues(self.context, {self.seed_issue.milestone: 1})

        self.assertIn(
            f"issue create failed for '{self.seed_issue.title}': validation failed",
            self.context.warnings,
        )

    def test_duplicate_repairs_cover_all_24_known_duplicates(self) -> None:
        self.assertEqual(len(setup.DUPLICATE_REPAIR_SPECS), 24)

    def test_duplicate_repair_comment_references_canonical_and_bug_issue(self) -> None:
        comment = setup.duplicate_repair_comment(2, 51)
        self.assertIn("Duplicate of #2.", comment)
        self.assertIn("Tracking der technischen Ursache: #51", comment)

    def test_duplicate_repair_refuses_unapproved_repository_without_writes(self) -> None:
        runner = MagicMock()
        with patch.object(setup, "run_gh", runner):
            allowed = setup.validate_duplicate_repair_repository(self.context)

        self.assertFalse(allowed)
        self.assertFalse(runner.called)

    def test_duplicate_repair_accepts_case_insensitive_repository_name(self) -> None:
        mixed_case = setup.GhContext(
            True,
            True,
            "pain1234/SAVE-MONEY-TRADING-BOT",
            False,
        )
        self.assertTrue(setup.validate_duplicate_repair_repository(mixed_case))

    def test_duplicate_repair_title_mismatch_blocks_mutation(self) -> None:
        runner = MagicMock(
            side_effect=[
                gh_result(stdout=issue_payload(17, "Wrong title")),
                gh_result(stdout=issue_payload(2, self.sample_repair.expected_title)),
            ]
        )
        with patch.object(setup, "DUPLICATE_REPAIR_SPECS", (self.sample_repair,)), patch.object(
            setup, "run_gh", runner
        ):
            exit_code = setup.repair_duplicate_issues(self.approved_context)

        self.assertEqual(exit_code, 1)
        self.assertFalse(any(is_mutating_gh_command(call.args[0]) for call in runner.call_args_list))

    def test_duplicate_repair_canonical_title_mismatch_blocks_mutation(self) -> None:
        runner = MagicMock(
            side_effect=[
                gh_result(stdout=issue_payload(17, self.sample_repair.expected_title)),
                gh_result(stdout=issue_payload(2, "Unexpected canonical title")),
            ]
        )
        with patch.object(setup, "DUPLICATE_REPAIR_SPECS", (self.sample_repair,)), patch.object(
            setup, "run_gh", runner
        ):
            exit_code = setup.repair_duplicate_issues(self.approved_context)

        self.assertEqual(exit_code, 1)
        self.assertFalse(any(is_mutating_gh_command(call.args[0]) for call in runner.call_args_list))

    def test_repair_skips_already_closed_duplicate(self) -> None:
        runner = MagicMock(
            return_value=gh_result(
                stdout=issue_payload(17, self.sample_repair.expected_title, state="CLOSED")
            )
        )
        with patch.object(setup, "DUPLICATE_REPAIR_SPECS", (self.sample_repair,)), patch.object(
            setup, "run_gh", runner
        ):
            exit_code = setup.repair_duplicate_issues(self.approved_context)

        self.assertEqual(exit_code, 0)
        self.assertEqual(runner.call_count, 1)
        self.assertFalse(any(is_mutating_gh_command(call.args[0]) for call in runner.call_args_list))

    def test_repair_apply_comments_and_closes_open_duplicate(self) -> None:
        runner = MagicMock(
            side_effect=[
                gh_result(stdout=issue_payload(17, self.sample_repair.expected_title)),
                gh_result(stdout=issue_payload(2, self.sample_repair.expected_title)),
                gh_result(returncode=0),
                gh_result(returncode=0),
            ]
        )
        with patch.object(setup, "DUPLICATE_REPAIR_SPECS", (self.sample_repair,)), patch.object(
            setup, "run_gh", runner
        ):
            exit_code = setup.repair_duplicate_issues(self.approved_context)

        self.assertEqual(exit_code, 0)
        close_args = [call.args[0] for call in runner.call_args_list if call.args[0][:2] == ["issue", "close"]]
        self.assertEqual(close_args, [["issue", "close", "17", "--repo", APPROVED_REPO, "--reason", "not planned"]])

    def test_skip_project_skips_try_create_project_without_warning(self) -> None:
        with patch.object(setup, "ensure_labels"), patch.object(
            setup, "ensure_milestones", return_value={}
        ), patch.object(setup, "ensure_seed_issues"), patch.object(
            setup, "try_create_project"
        ) as project_mock:
            exit_code = setup.run_normal_setup(self.context, skip_project=True)

        self.assertEqual(exit_code, 0)
        project_mock.assert_not_called()
        self.assertFalse(self.context.warnings)

    def test_workflow_apply_command_uses_skip_project(self) -> None:
        workflow_path = Path(__file__).resolve().parents[2] / ".github/workflows/github-governance-setup.yml"
        workflow_text = workflow_path.read_text(encoding="utf-8")
        self.assertIn("python scripts/github_project_setup.py --apply --skip-project", workflow_text)
        for line in workflow_text.splitlines():
            if "python scripts/github_project_setup.py --apply" in line:
                self.assertIn("--skip-project", line)
        self.assertNotIn("gh project list", workflow_text)
        self.assertNotIn("gh project create", workflow_text)

    def test_repair_mode_main_does_not_run_normal_setup(self) -> None:
        argv = ["github_project_setup.py", "--repair-duplicates", "--apply"]
        with patch.object(sys, "argv", argv), patch.object(
            setup, "build_context",
            return_value=setup.GhContext(True, True, APPROVED_REPO, False),
        ), patch.object(setup, "validate_duplicate_repair_repository", return_value=True), patch.object(
            setup, "repair_duplicate_issues", return_value=0
        ) as repair_mock, patch.object(setup, "ensure_labels") as labels_mock, patch.object(
            setup, "ensure_milestones"
        ) as milestones_mock, patch.object(setup, "ensure_seed_issues") as seeds_mock, patch.object(
            setup, "try_create_project"
        ) as project_mock:
            exit_code = setup.main()

        self.assertEqual(exit_code, 0)
        repair_mock.assert_called_once()
        labels_mock.assert_not_called()
        milestones_mock.assert_not_called()
        seeds_mock.assert_not_called()
        project_mock.assert_not_called()

    def test_repair_main_refuses_foreign_repository_with_exit_code_2(self) -> None:
        argv = ["github_project_setup.py", "--repair-duplicates", "--apply"]
        foreign_context = setup.GhContext(True, True, FOREIGN_REPO, False)
        with patch.object(sys, "argv", argv), patch.object(
            setup, "build_context", return_value=foreign_context
        ), patch.object(setup, "repair_duplicate_issues") as repair_mock, patch.object(
            setup, "run_gh"
        ) as runner:
            exit_code = setup.main()

        self.assertEqual(exit_code, 2)
        repair_mock.assert_not_called()
        self.assertFalse(runner.called)


if __name__ == "__main__":
    unittest.main()
