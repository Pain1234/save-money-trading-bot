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


def gh_result(
    stdout: str = "",
    stderr: str = "",
    returncode: int = 0,
) -> MagicMock:
    return MagicMock(stdout=stdout, stderr=stderr, returncode=returncode)


class GitHubProjectSetupTests(unittest.TestCase):
    def setUp(self) -> None:
        self.context = setup.GhContext(
            available=True,
            authenticated=True,
            repo="owner/repository",
            dry_run=False,
        )
        self.seed_issue = setup.SeedIssue(
            "test-governance-seed",
            f"{chr(0x00DC)}berpr{chr(0x00FC)}fung {chr(0x2013)} Seed Issue",
            "P0 – Governance and Scope Freeze",
            ("area:governance",),
            "Seed body",
        )

    def _ensure_single_seed_issue(self) -> MagicMock:
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
            setup.ensure_seed_issues(
                self.context,
                {self.seed_issue.milestone: 1},
            )
        return runner

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
        unauthenticated = setup.GhContext(True, False, "owner/repository", False)
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
        self.assertEqual(len(setup.DUPLICATE_REPAIRS), 24)

    def test_duplicate_repair_comment_references_canonical_and_bug_issue(self) -> None:
        comment = setup.duplicate_repair_comment(2, 51)
        self.assertIn("Duplicate of #2.", comment)
        self.assertIn("Tracking der technischen Ursache: #51", comment)

    def test_repair_duplicate_issues_dry_run_does_not_write(self) -> None:
        dry_context = setup.GhContext(True, True, "owner/repository", True)
        runner = MagicMock(
            return_value=gh_result(
                stdout=json.dumps({"number": 17, "state": "OPEN", "title": "dup", "body": ""})
            )
        )
        with patch.object(setup, "DUPLICATE_REPAIRS", {17: 2}), patch.object(setup, "run_gh", runner):
            setup.repair_duplicate_issues(dry_context)

        self.assertEqual(runner.call_count, 1)
        self.assertFalse(any(call.args[0][:2] == ["issue", "close"] for call in runner.call_args_list))

    def test_repair_skips_already_closed_duplicate(self) -> None:
        runner = MagicMock(
            return_value=gh_result(
                stdout=json.dumps({"number": 17, "state": "CLOSED", "title": "dup", "body": ""})
            )
        )
        with patch.object(setup, "DUPLICATE_REPAIRS", {17: 2}), patch.object(setup, "run_gh", runner):
            setup.repair_duplicate_issues(self.context)

        self.assertEqual(runner.call_count, 1)

    def test_repair_apply_comments_and_closes_open_duplicate(self) -> None:
        apply_context = setup.GhContext(True, True, "owner/repository", False)
        runner = MagicMock(
            side_effect=[
                gh_result(stdout=json.dumps({"number": 17, "state": "OPEN", "title": "dup", "body": ""})),
                gh_result(returncode=0),
                gh_result(returncode=0),
            ]
        )
        with patch.object(setup, "DUPLICATE_REPAIRS", {17: 2}), patch.object(setup, "run_gh", runner):
            setup.repair_duplicate_issues(apply_context)

        self.assertEqual(runner.call_count, 3)
        close_args = runner.call_args_list[2].args[0]
        self.assertEqual(close_args[:3], ["issue", "close", "17"])


if __name__ == "__main__":
    unittest.main()
