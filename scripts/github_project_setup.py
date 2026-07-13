#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""GitHub labels, milestones, and seed issues for project governance.

Uses GitHub CLI (gh) when available. Safe dry-run without authentication.

Usage:
    python scripts/github_project_setup.py --dry-run
    python scripts/github_project_setup.py --apply
    python scripts/github_project_setup.py --repair-duplicates --dry-run
    python scripts/github_project_setup.py --repair-duplicates --apply

Sequential idempotency is covered by automated tests. Official apply runs are
serialized through GitHub Actions concurrency. Uncoordinated parallel local
apply processes are not claimed to be fully atomic.

Normal setup never closes issues, deletes labels/milestones, or modifies branch
protection. The explicit ``--repair-duplicates`` mode closes only the configured
duplicate list after commenting.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import unicodedata
from dataclasses import dataclass, field
from typing import Any

PROJECT_NAME = "Trading System Roadmap"
GOVERNANCE_BUG_ISSUE = 51
DUPLICATE_REPAIR_REPOSITORY = "Pain1234/save-money-trading-bot"
SEED_ISSUE_MARKER = "<!-- governance-seed-issue -->"
SEED_KEY_MARKER_PREFIX = "<!-- governance-seed-key:"
PHASE_KEY_PATTERN = re.compile(r"^(P\d+)")


@dataclass(frozen=True)
class SeedIssue:
    key: str
    title: str
    milestone: str
    labels: tuple[str, ...]
    body: str


# This migration is deliberately restricted to the repository that received
# the original unkeyed governance seeds. Do not use it for similarly titled
# issues in any other repository.
CANONICAL_SEED_ISSUES: dict[str, dict[str, int]] = {
    "Pain1234/save-money-trading-bot": {
        "p0-repository-governance": 2,
        "p0-verify-current-system-architecture": 3,
        "p0-document-and-freeze-strategy-parameters": 4,
        "p0-make-definition-of-done-binding": 5,
        "p0-review-initial-risk-register": 6,
        "p1-document-reproducible-baseline-start": 7,
        "p1-review-runtime-and-dependency-versions": 8,
        "p1-inventory-existing-test-and-ci-coverage": 9,
        "p1-define-reproducible-baseline-release": 10,
        "p2-review-backup-and-restore-process": 11,
        "p2-document-reconciliation-requirements": 12,
        "p2-review-idempotency-of-critical-processing-paths": 13,
        "p2-test-worker-restart-after-process-abort": 14,
        "p2-capture-incident-and-runbook-gaps": 15,
        "p2-define-critical-operational-metrics": 16,
    }
}

@dataclass(frozen=True)
class DuplicateRepair:
    duplicate_number: int
    canonical_number: int
    expected_title: str
    seed_key: str


# Only these known duplicate issues may be repaired automatically. Each entry
# requires duplicate and canonical issue identity verification before mutation.
_DUPLICATE_REPAIR_GROUPS: tuple[tuple[int, str, str, tuple[int, ...]], ...] = (
    (2, "p0-repository-governance", "Repository-Governance einführen", (17, 23, 30, 37)),
    (6, "p0-review-initial-risk-register", "Risk Register initial prüfen", (18, 24, 31, 38)),
    (8, "p1-review-runtime-and-dependency-versions", "Laufzeit- und Abhängigkeitsversionen prüfen", (19, 25, 32, 39)),
    (11, "p2-review-backup-and-restore-process", "Backup- und Restore-Prozess prüfen", (20, 26, 33, 40)),
    (13, "p2-review-idempotency-of-critical-processing-paths", "Idempotenz kritischer Verarbeitungspfade prüfen", (21, 27, 34, 41)),
    (15, "p2-capture-incident-and-runbook-gaps", "Incident- und Runbook-Lücken erfassen", (22, 28, 35, 42)),
)

DUPLICATE_REPAIR_SPECS: tuple[DuplicateRepair, ...] = tuple(
    DuplicateRepair(
        duplicate_number=duplicate_number,
        canonical_number=canonical_number,
        expected_title=expected_title,
        seed_key=seed_key,
    )
    for canonical_number, seed_key, expected_title, duplicate_numbers in _DUPLICATE_REPAIR_GROUPS
    for duplicate_number in duplicate_numbers
)

# Legacy mapping retained for tests and migration references only.
DUPLICATE_REPAIRS: dict[int, int] = {
    repair.duplicate_number: repair.canonical_number
    for repair in DUPLICATE_REPAIR_SPECS
}

LABELS: list[tuple[str, str, str]] = [
    # (name, color without #, description)
    ("type:bug", "d73a4a", "Software defect"),
    ("type:feature", "0075ca", "Feature or roadmap task"),
    ("type:research", "7057ff", "Research experiment"),
    ("type:operations", "fbca04", "Operations or runbook work"),
    ("type:documentation", "0075ca", "Documentation only"),
    ("type:incident", "b60205", "Incident record"),
    ("area:data", "1d76db", "Market data pipeline"),
    ("area:research", "5319e7", "Research and backtest"),
    ("area:strategy", "006b75", "Strategy logic and specs"),
    ("area:risk", "e99695", "Risk engine and limits"),
    ("area:execution", "f9d0c4", "Order and fill execution"),
    ("area:accounting", "c2e0c6", "Wallet, PnL, positions"),
    ("area:monitoring", "bfdadc", "Observability and health"),
    ("area:dashboard", "d4c5f9", "Dashboard UI"),
    ("area:infrastructure", "0366d6", "Deploy, DB, infra"),
    ("area:security", "ee0701", "Security and secrets"),
    ("area:governance", "0e8a16", "Project governance"),
    ("severity:S1-critical", "b60205", "Critical severity"),
    ("severity:S2-high", "d93f0b", "High severity"),
    ("severity:S3-medium", "fbca04", "Medium severity"),
    ("severity:S4-low", "0e8a16", "Low severity"),
    ("status:blocked", "000000", "Blocked"),
    ("status:needs-decision", "5319e7", "Needs human decision"),
    ("status:needs-evidence", "1d76db", "Needs evidence"),
    ("status:invalidated", "666666", "Invalidated result"),
    ("agent:cursor", "cfd3d7", "Work by Cursor agent"),
    ("agent:codex-review", "cfd3d7", "Codex review"),
    ("human-approval-required", "b60205", "Requires explicit human approval"),
]

MILESTONES: list[tuple[str, str]] = [
    ("P0 – Governance and Scope Freeze", "Binding roadmap, issues, PR process, scope freeze"),
    ("P1 – Reproducible Baseline Release", "Reproducible paper baseline tag and docs"),
    ("P2 – Operational Reliability", "Backup, reconciliation, runbooks, restart safety"),
    ("P3 – Versioned Historical Market Data", "Dataset manifests and reproducible imports"),
    ("P4 – Research Engine", "Standardized experiment pipeline"),
    ("P5 – Honest Validation of Trend Strategy V1", "OOS, walk-forward, stress tests"),
    ("P6 – Paper Trading Soak", "90-day paper soak with reconciliation"),
    ("P7 – Independent Strategy Candidates", "Uncorrelated strategy hypotheses"),
    ("P8 – Separate Micro-Live System", "Micro-live — human approval required"),
    ("P9 – Controlled Scaling", "Evidence-based scaling — human approval required"),
]

# Seed issues are keyed so duplicate detection does not depend on localized
# titles or historical encoding variants.
SEED_ISSUES: list[SeedIssue] = [
    SeedIssue(
        "p0-repository-governance",
        "Repository-Governance einführen",
        "P0 – Governance and Scope Freeze",
        ("type:documentation", "area:governance"),
        """## Hintergrund
GitHub soll verbindliche Quelle für Roadmap, Aufgaben und Entscheidungen werden.

## Scope
- Merge governance docs (ROADMAP, AGENTS, templates, setup script)
- Labels, milestones, seed issues via setup script

## Nicht-Scope
- Handelslogik, Strategieparameter, Migrationen, Live-Trading

## Akzeptanzkriterien
- [ ] Governance PR merged
- [ ] `python scripts/github_project_setup.py --apply` erfolgreich
- [ ] Team nutzt Issue/PR-Workflow
""",
    ),
    SeedIssue(
        "p0-verify-current-system-architecture",
        "Aktuelle Systemarchitektur verifizieren",
        "P0 – Governance and Scope Freeze",
        ("type:documentation", "area:governance"),
        """## Hintergrund
`docs/ARCHITECTURE.md` muss dem tatsächlichen Code entsprechen.

## Scope
- Review modules under `services/`
- Update architecture doc gaps

## Nicht-Scope
- Refactoring

## Akzeptanzkriterien
- [ ] Each production entrypoint documented
- [ ] Current Gap sections accurate
- [ ] Linked from README or AGENTS.md
""",
    ),
    SeedIssue(
        "p0-document-and-freeze-strategy-parameters",
        "Bestehende Strategieparameter dokumentieren und einfrieren",
        "P0 – Governance and Scope Freeze",
        ("type:documentation", "area:strategy", "status:needs-decision"),
        """## Hintergrund
Strategy V1 parameters must be explicit and change-controlled.

## Scope
- Extract parameters from `docs/strategy-specification.md` and code
- Document freeze policy in issue/ADR

## Nicht-Scope
- Parameter tuning

## Akzeptanzkriterien
- [ ] Parameter inventory published
- [ ] Change process requires issue + review
- [ ] AGENTS.md references freeze
""",
    ),
    SeedIssue(
        "p0-make-definition-of-done-binding",
        "Definition of Done verbindlich machen",
        "P0 – Governance and Scope Freeze",
        ("type:documentation", "area:governance"),
        """## Hintergrund
`docs/DEFINITION_OF_DONE.md` exists; adoption needed.

## Scope
- PR template checklist enforced in review
- Optional CI comment (future)

## Akzeptanzkriterien
- [ ] Test evidence in three post-governance baseline PRs (#50, #54, #57 — ADR-011)
- [ ] Reviewers reject PRs missing test evidence
""",
    ),
    SeedIssue(
        "p0-review-initial-risk-register",
        "Risk Register initial prüfen",
        "P0 – Governance and Scope Freeze",
        ("type:documentation", "area:governance", "area:risk"),
        """## Hintergrund
`docs/RISK_REGISTER.md` seeded; top risks need owners and issues.

## Scope
- Link top 5 risks to GitHub issues
- Mark status open/planned/partial honestly

## Akzeptanzkriterien
- [ ] R-001 through R-005 have linked issues or justified deferral
""",
    ),
    SeedIssue(
        "p1-document-reproducible-baseline-start",
        "Reproduzierbaren Baseline-Start dokumentieren",
        "P1 – Reproducible Baseline Release",
        ("type:documentation", "area:infrastructure"),
        """## Hintergrund
README is stale; production paths are in deploy docs.

## Scope
- Document worker/API/dashboard start from `deploy/scripts/`
- Align README with PostgreSQL/Railway architecture

## Nicht-Scope
- Changing start commands

## Akzeptanzkriterien
- [ ] Fresh clone + documented env vars can start paper stack locally OR clear minimum env documented
""",
    ),
    SeedIssue(
        "p1-review-runtime-and-dependency-versions",
        "Laufzeit- und Abhängigkeitsversionen prüfen",
        "P1 – Reproducible Baseline Release",
        ("type:operations", "area:infrastructure"),
        """## Scope
- Pin/document Python 3.12, Node 22, dependency lock strategy

## Akzeptanzkriterien
- [ ] Versions recorded in baseline doc or tag notes
""",
    ),
    SeedIssue(
        "p1-inventory-existing-test-and-ci-coverage",
        "Bestehende Test- und CI-Abdeckung erfassen",
        "P1 – Reproducible Baseline Release",
        ("type:documentation", "area:governance"),
        """## Scope
- Document pytest markers, known failures, missing CI gap

## Akzeptanzkriterien
- [ ] Test commands in README/AGENTS accurate
- [ ] Known bulk postgres failures documented if still present
""",
    ),
    SeedIssue(
        "p1-define-reproducible-baseline-release",
        "Reproduzierbaren Baseline-Release definieren",
        "P1 – Reproducible Baseline Release",
        ("type:feature", "area:governance"),
        """## Scope
- Define tag naming and exit criteria for baseline-paper-v*

## Akzeptanzkriterien
- [ ] Tag created on agreed commit
- [ ] CHANGELOG notes baseline
""",
    ),
    SeedIssue(
        "p2-review-backup-and-restore-process",
        "Backup- und Restore-Prozess prüfen",
        "P2 – Operational Reliability",
        ("type:operations", "area:infrastructure"),
        """## Scope
- Railway Postgres backup; restore drill once

## Akzeptanzkriterien
- [ ] Runbook section in `docs/runbooks/README.md` complete
- [ ] Restore tested on non-prod
""",
    ),
    SeedIssue(
        "p2-document-reconciliation-requirements",
        "Reconciliation-Anforderungen dokumentieren",
        "P2 – Operational Reliability",
        ("type:documentation", "area:accounting"),
        """## Scope
- Daily reconciliation checklist for paper soak

## Akzeptanzkriterien
- [ ] Procedure documented
- [ ] Owner and frequency defined
""",
    ),
    SeedIssue(
        "p2-review-idempotency-of-critical-processing-paths",
        "Idempotenz kritischer Verarbeitungspfade prüfen",
        "P2 – Operational Reliability",
        ("type:feature", "area:execution"),
        """## Scope
- Review fills, scheduler runs, portfolio snapshots for duplicate safety

## Akzeptanzkriterien
- [ ] Test coverage noted or gaps filed as bugs
""",
    ),
    SeedIssue(
        "p2-test-worker-restart-after-process-abort",
        "Worker-Wiederanlauf nach Prozessabbruch testen",
        "P2 – Operational Reliability",
        ("type:operations", "area:execution"),
        """## Scope
- Kill worker mid-run; verify recovery and no duplicate entries

## Akzeptanzkriterien
- [ ] Test automated or runbook with recorded result
""",
    ),
    SeedIssue(
        "p2-capture-incident-and-runbook-gaps",
        "Incident- und Runbook-Lücken erfassen",
        "P2 – Operational Reliability",
        ("type:documentation", "area:governance"),
        """## Scope
- Complete TODO runbooks in `docs/runbooks/README.md`

## Akzeptanzkriterien
- [ ] Each critical op has issue or completed runbook
""",
    ),
    SeedIssue(
        "p2-define-critical-operational-metrics",
        "Kritische Betriebsmetriken definieren",
        "P2 – Operational Reliability",
        ("type:feature", "area:monitoring"),
        """## Scope
- heartbeat age, readiness state, reconnect count, DB fingerprint drift

## Akzeptanzkriterien
- [ ] Metrics list documented
- [ ] Dashboard or API fields mapped
""",
    ),
]


@dataclass
class GhContext:
    available: bool
    authenticated: bool
    repo: str  # owner/name
    dry_run: bool
    warnings: list[str] = field(default_factory=list)

    def log(self, msg: str) -> None:
        prefix = "[dry-run] " if self.dry_run else ""
        print(f"{prefix}{msg}")

    def warn(self, msg: str) -> None:
        self.warnings.append(msg)
        self.log(f"WARN: {msg}")


def _repair_mojibake(text: str) -> str:
    """Repair common double-encoded UTF-8 strings from older gh/Windows runs."""
    repaired = text
    for _ in range(2):
        try:
            candidate = repaired.encode("latin1").decode("utf-8")
        except (UnicodeDecodeError, UnicodeEncodeError):
            break
        if candidate == repaired:
            break
        repaired = candidate
    return repaired


def normalize_repository_name(value: str) -> str:
    """Normalize repository names for case-insensitive comparison."""
    return value.strip().casefold()


def validate_duplicate_repair_repository(ctx: GhContext) -> bool:
    """Ensure duplicate repair runs only in the approved repository."""
    expected = normalize_repository_name(DUPLICATE_REPAIR_REPOSITORY)
    actual = normalize_repository_name(ctx.repo)
    if actual != expected:
        ctx.warn(
            "duplicate repair is restricted to "
            f"{DUPLICATE_REPAIR_REPOSITORY}; refusing repository {ctx.repo}"
        )
        return False
    return True


def normalize_title(text: str) -> str:
    """Normalize titles for idempotent matching across encodings."""
    text = _repair_mojibake(text)
    text = unicodedata.normalize("NFKC", text)
    text = text.replace("\u2013", "-").replace("\u2014", "-")
    text = re.sub(r"\s+", " ", text).strip().casefold()
    return text


def milestone_phase_key(title: str) -> str | None:
    match = PHASE_KEY_PATTERN.match(title.strip())
    return match.group(1) if match else None


def seed_key_marker(key: str) -> str:
    """Return the stable, machine-readable marker for a governance seed."""
    return f"{SEED_KEY_MARKER_PREFIX}{key} -->"


def parse_seed_key_from_body(body: str | None) -> str | None:
    """Extract a seed key from an issue body, if present."""
    if not isinstance(body, str):
        return None
    match = re.search(r"<!--\s*governance-seed-key:\s*([a-z0-9][a-z0-9-]*)\s*-->", body)
    return match.group(1) if match else None


def with_seed_body(seed: SeedIssue | str, body: str | None = None) -> str:
    """Prefix a body with both current and legacy governance seed markers."""
    if isinstance(seed, SeedIssue):
        key, original_body = seed.key, seed.body
    else:
        if body is None:
            raise ValueError("body is required when passing a seed key")
        key, original_body = seed, body
    markers = (seed_key_marker(key), SEED_ISSUE_MARKER)
    prefix = "\n".join(marker for marker in markers if marker not in original_body)
    return f"{prefix}\n\n{original_body.lstrip()}" if prefix else original_body


def run_gh(args: list[str], *, check: bool = False) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["gh", *args],
        capture_output=True,
        text=True,
        check=check,
    )


def gh_available() -> bool:
    try:
        subprocess.run(["gh", "--version"], capture_output=True, check=True)
        return True
    except (FileNotFoundError, subprocess.CalledProcessError):
        return False


def gh_authenticated() -> bool:
    try:
        result = run_gh(["auth", "status"], check=False)
        return result.returncode == 0
    except FileNotFoundError:
        return False


def detect_repo() -> str | None:
    try:
        result = run_gh(["repo", "view", "--json", "nameWithOwner", "-q", ".nameWithOwner"], check=False)
        if result.returncode == 0:
            repo = result.stdout.strip()
            return repo if repo else None
    except FileNotFoundError:
        pass
    return None


def list_labels(ctx: GhContext) -> dict[str, dict[str, Any]]:
    if not ctx.available or not ctx.authenticated:
        return {}
    result = run_gh(["label", "list", "--repo", ctx.repo, "--limit", "200", "--json", "name,color,description"], check=False)
    if result.returncode != 0:
        ctx.warn(f"could not list labels: {result.stderr.strip()}")
        return {}
    items = json.loads(result.stdout or "[]")
    return {item["name"]: item for item in items}


def ensure_labels(ctx: GhContext) -> None:
    existing = list_labels(ctx)
    for name, color, description in LABELS:
        if name in existing:
            ctx.log(f"label exists: {name}")
            continue
        ctx.log(f"create label: {name}")
        if ctx.dry_run or not ctx.authenticated:
            continue
        result = run_gh(
            [
                "label",
                "create",
                name,
                "--repo",
                ctx.repo,
                "--color",
                color,
                "--description",
                description,
            ],
            check=False,
        )
        if result.returncode != 0:
            # Most common: already exists (race), or insufficient permissions.
            ctx.warn(f"label create failed for '{name}': {result.stderr.strip()}")


def list_milestones(ctx: GhContext) -> dict[str, dict[str, Any]]:
    if not ctx.available or not ctx.authenticated:
        return {}
    # Use a stable JSON response to avoid CLI output variations.
    result = run_gh(["api", f"repos/{ctx.repo}/milestones?state=all&per_page=100"], check=False)
    if result.returncode != 0:
        ctx.warn(f"could not list milestones: {result.stderr.strip()}")
        return {}
    try:
        items = json.loads(result.stdout or "[]")
    except json.JSONDecodeError:
        ctx.warn("could not parse milestones JSON")
        return {}
    milestones: dict[str, dict[str, Any]] = {}
    if isinstance(items, list):
        for item in items:
            if isinstance(item, dict) and "title" in item:
                milestones[item["title"]] = item
    return milestones


def _milestone_maps(existing: dict[str, dict[str, Any]]) -> tuple[dict[str, int], dict[str, int]]:
    """Return (title->number, phase_key->number) maps for milestone matching."""
    title_to_number = {title: milestone["number"] for title, milestone in existing.items()}
    phase_to_number: dict[str, int] = {}
    for title, milestone in existing.items():
        phase_key = milestone_phase_key(title)
        if phase_key is not None:
            phase_to_number.setdefault(phase_key, milestone["number"])
    return title_to_number, phase_to_number


def ensure_milestones(ctx: GhContext) -> dict[str, int]:
    existing = list_milestones(ctx)
    title_to_number, phase_to_number = _milestone_maps(existing)
    for title, description in MILESTONES:
        phase_key = milestone_phase_key(title)
        if title in title_to_number or (phase_key is not None and phase_key in phase_to_number):
            ctx.log(f"milestone exists: {title}")
            continue
        ctx.log(f"create milestone: {title}")
        if ctx.dry_run or not ctx.authenticated:
            continue
        result = run_gh(
            [
                "api",
                f"repos/{ctx.repo}/milestones",
                "-f",
                f"title={title}",
                "-f",
                f"description={description}",
            ],
            check=False,
        )
        if result.returncode != 0:
            # Common: 422 validation failed (already exists), or missing scopes.
            ctx.warn(f"milestone create failed for '{title}': {result.stderr.strip()}")
            # If it already exists, we'll pick it up in the refresh below.
            continue
        try:
            created = json.loads(result.stdout)
        except json.JSONDecodeError:
            ctx.warn(f"milestone create returned non-JSON for '{title}'")
            continue
        if isinstance(created, dict) and "number" in created:
            title_to_number[title] = created["number"]
            if phase_key is not None:
                phase_to_number[phase_key] = created["number"]
    # refresh if we created any
    if not ctx.dry_run and ctx.authenticated:
        refreshed = list_milestones(ctx)
        title_to_number, phase_to_number = _milestone_maps(refreshed)
    return {title: phase_to_number[phase_key] for title, _ in MILESTONES if (phase_key := milestone_phase_key(title)) in phase_to_number}


def load_all_issues(ctx: GhContext) -> list[dict[str, Any]] | None:
    """Load every issue across all states, excluding pull requests."""
    if not ctx.available or not ctx.authenticated:
        return []
    issues: list[dict[str, Any]] = []
    page = 1
    while True:
        result = run_gh(
            ["api", f"repos/{ctx.repo}/issues?state=all&per_page=100&page={page}"],
            check=False,
        )
        if result.returncode != 0:
            ctx.warn(f"could not list issues: {result.stderr.strip()}")
            return None
        try:
            items = json.loads(result.stdout or "[]")
        except json.JSONDecodeError:
            ctx.warn("could not parse issues JSON")
            return None
        if not isinstance(items, list):
            ctx.warn("unexpected issues JSON shape")
            return None
        issues.extend(
            item for item in items
            if isinstance(item, dict) and "pull_request" not in item
        )
        if len(items) < 100:
            return issues
        page += 1


def find_seed_issue(
    seed: SeedIssue,
    issues: list[dict[str, Any]],
    repo: str,
) -> dict[str, Any] | None:
    """Find a seed issue by marker, repo-scoped migration, then title."""
    for issue in issues:
        if parse_seed_key_from_body(issue.get("body")) == seed.key:
            return issue

    canonical_number = CANONICAL_SEED_ISSUES.get(repo, {}).get(seed.key)
    if canonical_number is not None:
        for issue in issues:
            if issue.get("number") == canonical_number:
                return issue

    wanted_title = normalize_title(seed.title)
    for issue in issues:
        title = issue.get("title")
        if isinstance(title, str) and normalize_title(title) == wanted_title:
            return issue
    return None


def ensure_seed_issues(ctx: GhContext, milestone_numbers: dict[str, int]) -> None:
    issues = load_all_issues(ctx)
    if issues is None:
        return
    for seed in SEED_ISSUES:
        found = find_seed_issue(seed, issues, ctx.repo)
        if found is not None:
            number = found.get("number", "?")
            ctx.log(f"FOUND canonical issue #{number} for seed {seed.key}")
            ctx.log("SKIP duplicate creation")
            continue

        # A concurrent run may create the same issue after the first load.
        refreshed_issues = load_all_issues(ctx)
        if refreshed_issues is None:
            return
        issues = refreshed_issues
        found = find_seed_issue(seed, issues, ctx.repo)
        if found is not None:
            number = found.get("number", "?")
            ctx.log(f"FOUND canonical issue #{number} for seed {seed.key}")
            ctx.log("SKIP duplicate creation")
            continue

        if ctx.dry_run:
            ctx.log(f"WOULD CREATE seed {seed.key}: {seed.title}")
            continue
        ctx.log(f"create issue: {seed.title}")
        if ctx.dry_run or not ctx.authenticated:
            continue
        args = [
            "issue",
            "create",
            "--repo",
            ctx.repo,
            "--title",
            seed.title,
            "--body",
            with_seed_body(seed),
        ]
        for label in seed.labels:
            args.extend(["--label", label])
        ms_num = milestone_numbers.get(seed.milestone)
        if ms_num is not None:
            args.extend(["--milestone", seed.milestone])
        result = run_gh(args, check=False)
        if result.returncode != 0:
            ctx.warn(f"issue create failed for '{seed.title}': {result.stderr.strip()}")
            continue
        try:
            created_number: int | None = int(result.stdout.rstrip("/\n").split("/")[-1])
        except ValueError:
            created_number = None
        # Keep the newly-created issue in memory so this invocation cannot
        # create it again even when the create response is not a standard URL.
        issues.append({"number": created_number, "title": seed.title, "body": with_seed_body(seed)})


def duplicate_repair_comment(canonical_number: int, bug_issue: int = GOVERNANCE_BUG_ISSUE) -> str:
    """Return the standard duplicate-closure comment for governance seed issues."""
    return (
        f"Duplicate of #{canonical_number}.\n"
        "Dieses Issue wurde durch einen früheren fehlerhaften oder konkurrierenden\n"
        "Lauf der Governance-Automatisierung erzeugt.\n"
        "Einzigartige Informationen wurden vor dem Schließen geprüft und, sofern\n"
        "vorhanden, in das kanonische Issue übernommen.\n"
        f"Tracking der technischen Ursache: #{bug_issue}"
    )


def load_issue_summary(ctx: GhContext, number: int) -> dict[str, Any] | None:
    """Load issue state/title/body for duplicate repair decisions."""
    if not ctx.available or not ctx.authenticated:
        return None
    result = run_gh(
        [
            "issue",
            "view",
            str(number),
            "--repo",
            ctx.repo,
            "--json",
            "number,state,title,body",
        ],
        check=False,
    )
    if result.returncode != 0:
        ctx.warn(f"could not load issue #{number}: {result.stderr.strip()}")
        return None
    try:
        issue = json.loads(result.stdout or "{}")
    except json.JSONDecodeError:
        ctx.warn(f"could not parse issue JSON for #{number}")
        return None
    return issue if isinstance(issue, dict) else None


def verify_duplicate_repair_identity(
    ctx: GhContext,
    repair: DuplicateRepair,
    duplicate_issue: dict[str, Any],
    canonical_issue: dict[str, Any],
) -> bool:
    """Verify duplicate/canonical issue identity before any mutation."""
    duplicate_number = duplicate_issue.get("number")
    canonical_number = canonical_issue.get("number")
    if duplicate_number != repair.duplicate_number:
        ctx.warn(
            f"duplicate repair #{repair.duplicate_number}: loaded duplicate issue "
            f"#{duplicate_number} does not match configured number"
        )
        return False
    if canonical_number != repair.canonical_number:
        ctx.warn(
            f"duplicate repair #{repair.duplicate_number}: loaded canonical issue "
            f"#{canonical_number} does not match configured number"
        )
        return False
    if repair.duplicate_number == repair.canonical_number:
        ctx.warn(
            f"duplicate repair #{repair.duplicate_number}: duplicate and canonical "
            "numbers must differ"
        )
        return False

    expected_title = normalize_title(repair.expected_title)
    duplicate_title = duplicate_issue.get("title")
    canonical_title = canonical_issue.get("title")
    if not isinstance(duplicate_title, str) or normalize_title(duplicate_title) != expected_title:
        ctx.warn(
            f"duplicate repair #{repair.duplicate_number}: duplicate title "
            f"{duplicate_title!r} does not match expected {repair.expected_title!r}"
        )
        return False
    if not isinstance(canonical_title, str) or normalize_title(canonical_title) != expected_title:
        ctx.warn(
            f"duplicate repair #{repair.duplicate_number}: canonical title "
            f"{canonical_title!r} does not match expected {repair.expected_title!r}"
        )
        return False
    return True


def comment_duplicate_issue(ctx: GhContext, duplicate_number: int, comment: str) -> bool:
    """Comment on a duplicate issue."""
    if ctx.dry_run or not ctx.authenticated:
        return True
    result = run_gh(
        [
            "issue",
            "comment",
            str(duplicate_number),
            "--repo",
            ctx.repo,
            "--body",
            comment,
        ],
        check=False,
    )
    if result.returncode != 0:
        ctx.warn(
            f"duplicate comment failed for #{duplicate_number}: "
            f"{result.stderr.strip()}"
        )
        return False
    return True


def close_duplicate_issue(ctx: GhContext, duplicate_number: int) -> bool:
    """Close a duplicate issue as not planned."""
    if ctx.dry_run or not ctx.authenticated:
        return True
    result = run_gh(
        [
            "issue",
            "close",
            str(duplicate_number),
            "--repo",
            ctx.repo,
            "--reason",
            "not planned",
        ],
        check=False,
    )
    if result.returncode != 0:
        ctx.warn(
            f"duplicate close failed for #{duplicate_number}: "
            f"{result.stderr.strip()}"
        )
        return False
    return True


def repair_duplicate_issues(ctx: GhContext) -> int:
    """Comment and close only configured duplicate governance seed issues."""
    failures = 0
    for repair in sorted(DUPLICATE_REPAIR_SPECS, key=lambda item: item.duplicate_number):
        duplicate_issue = load_issue_summary(ctx, repair.duplicate_number)
        if duplicate_issue is None:
            failures += 1
            continue

        state = str(duplicate_issue.get("state", "")).upper()
        if state == "CLOSED":
            ctx.log(f"SKIP duplicate #{repair.duplicate_number}: already closed")
            continue

        canonical_issue = load_issue_summary(ctx, repair.canonical_number)
        if canonical_issue is None:
            failures += 1
            continue

        if not verify_duplicate_repair_identity(ctx, repair, duplicate_issue, canonical_issue):
            failures += 1
            continue

        if ctx.dry_run:
            ctx.log(
                f"WOULD COMMENT on duplicate #{repair.duplicate_number} "
                f"(canonical #{repair.canonical_number})"
            )
            ctx.log(f"WOULD CLOSE DUPLICATE #{repair.duplicate_number}")
            continue

        ctx.log(
            f"comment duplicate #{repair.duplicate_number} -> "
            f"canonical #{repair.canonical_number}"
        )
        comment = duplicate_repair_comment(repair.canonical_number)
        if not comment_duplicate_issue(ctx, repair.duplicate_number, comment):
            failures += 1
            continue

        ctx.log(f"close duplicate #{repair.duplicate_number} as not planned")
        if not close_duplicate_issue(ctx, repair.duplicate_number):
            failures += 1

    return 1 if failures else 0


def run_normal_setup(ctx: GhContext, *, skip_project: bool) -> int:
    """Apply labels, milestones, seed issues, and optional project setup."""
    ensure_labels(ctx)
    milestone_numbers = ensure_milestones(ctx)
    ensure_seed_issues(ctx, milestone_numbers)
    if skip_project:
        ctx.log("skip GitHub Project operation: --skip-project")
    else:
        try_create_project(ctx)

    if ctx.dry_run:
        print("Dry-run complete. Re-run with --apply after `gh auth login`.")
        return 0
    if not ctx.authenticated:
        print("Apply requested but gh not authenticated. No changes made.")
        return 1
    if ctx.warnings:
        print(f"Apply finished with {len(ctx.warnings)} warning(s).")
        return 1
    print("Apply complete.")
    return 0


def try_create_project(ctx: GhContext) -> None:
    """Attempt GitHub Project v2 creation if permissions allow."""
    if ctx.dry_run or not ctx.authenticated:
        ctx.log(f"skip project creation (dry-run or not authenticated): {PROJECT_NAME}")
        return
    # List existing projects for repo owner
    owner = ctx.repo.split("/")[0]
    result = run_gh(
        ["project", "list", "--owner", owner, "--format", "json"],
        check=False,
    )
    if result.returncode != 0:
        ctx.warn(f"cannot list projects (need `project` scope?): {result.stderr.strip()}")
        ctx.log("Manual steps: see docs/PROJECT_OPERATING_SYSTEM.md")
        return
    try:
        payload = json.loads(result.stdout or "[]")
    except json.JSONDecodeError:
        payload = []
    if isinstance(payload, dict):
        projects = payload.get("projects", [])
    elif isinstance(payload, list):
        projects = payload
    else:
        projects = []
    if not isinstance(projects, list):
        ctx.warn("unexpected projects JSON shape; skipping project automation")
        ctx.log("Manual steps: see docs/PROJECT_OPERATING_SYSTEM.md")
        return
    for p in projects:
        # Some gh versions may return a list of strings; ignore those safely.
        if not isinstance(p, dict):
            continue
        if p.get("title") == PROJECT_NAME or p.get("name") == PROJECT_NAME:
            ctx.log(f"project exists: {PROJECT_NAME}")
            return
    ctx.log(f"create project: {PROJECT_NAME}")
    create = run_gh(
        ["project", "create", "--owner", owner, "--title", PROJECT_NAME, "--format", "json"],
        check=False,
    )
    if create.returncode != 0:
        ctx.warn(f"project create failed: {create.stderr.strip()}")
        ctx.log("Manual steps: see docs/PROJECT_OPERATING_SYSTEM.md")
        return
    ctx.log("project created — configure fields/views manually per docs/PROJECT_OPERATING_SYSTEM.md")


def build_context(dry_run: bool) -> GhContext:
    available = gh_available()
    authenticated = gh_authenticated() if available else False
    repo = detect_repo() if available and authenticated else ""
    if not repo and available:
        preview_ctx = GhContext(available, authenticated, "", dry_run)
        preview_ctx.warn("could not detect repo — use dry-run preview only")
    return GhContext(available, authenticated, repo or "UNKNOWN/UNKNOWN", dry_run)


def main() -> int:
    parser = argparse.ArgumentParser(description="Setup GitHub labels, milestones, and seed issues")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--dry-run", action="store_true", help="Preview actions without writes")
    group.add_argument("--apply", action="store_true", help="Apply changes via gh")
    parser.add_argument(
        "--repair-duplicates",
        action="store_true",
        help="Comment and close the 24 known duplicate governance seed issues",
    )
    parser.add_argument(
        "--skip-project",
        action="store_true",
        help="Skip GitHub Projects v2 discovery and creation",
    )
    args = parser.parse_args()
    dry_run = args.dry_run

    ctx = build_context(dry_run)

    print("=== GitHub Project Setup ===")
    print(f"gh installed: {ctx.available}")
    print(f"gh authenticated: {ctx.authenticated}")
    print(f"repository: {ctx.repo}")
    print(f"mode: {'dry-run' if dry_run else 'apply'}")
    print()

    if not ctx.available:
        print("GitHub CLI (gh) not found. Install from https://cli.github.com/")
        print("Dry-run will print planned labels, milestones, and issues only.")
        print()

    if args.repair_duplicates:
        if not validate_duplicate_repair_repository(ctx):
            print()
            print("Duplicate repair refused for this repository.")
            return 2
        exit_code = repair_duplicate_issues(ctx)
        print()
        if exit_code == 0:
            if dry_run:
                print("Duplicate repair dry-run complete.")
            else:
                print("Duplicate repair complete.")
        else:
            print("Duplicate repair finished with errors.")
        return exit_code

    exit_code = run_normal_setup(ctx, skip_project=args.skip_project)
    print()
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
