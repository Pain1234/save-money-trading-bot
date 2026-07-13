#!/usr/bin/env python3
"""Idempotent GitHub labels, milestones, and seed issues for project governance.

Uses GitHub CLI (gh) when available. Safe dry-run without authentication.

Usage:
    python scripts/github_project_setup.py --dry-run
    python scripts/github_project_setup.py --apply

Never closes issues, deletes labels/milestones, or modifies branch protection.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import dataclass
from typing import Any

PROJECT_NAME = "Trading System Roadmap"

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

# Seed issues: (title, milestone_title, labels, body)
SEED_ISSUES: list[tuple[str, str, list[str], str]] = [
    (
        "Repository-Governance einführen",
        "P0 – Governance and Scope Freeze",
        ["type:documentation", "area:governance"],
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
    (
        "Aktuelle Systemarchitektur verifizieren",
        "P0 – Governance and Scope Freeze",
        ["type:documentation", "area:governance"],
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
    (
        "Bestehende Strategieparameter dokumentieren und einfrieren",
        "P0 – Governance and Scope Freeze",
        ["type:documentation", "area:strategy", "status:needs-decision"],
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
    (
        "Definition of Done verbindlich machen",
        "P0 – Governance and Scope Freeze",
        ["type:documentation", "area:governance"],
        """## Hintergrund
`docs/DEFINITION_OF_DONE.md` exists; adoption needed.

## Scope
- PR template checklist enforced in review
- Optional CI comment (future)

## Akzeptanzkriterien
- [ ] DoD referenced in first 3 merged PRs after governance
- [ ] Reviewers reject PRs missing test evidence
""",
    ),
    (
        "Risk Register initial prüfen",
        "P0 – Governance and Scope Freeze",
        ["type:documentation", "area:governance", "area:risk"],
        """## Hintergrund
`docs/RISK_REGISTER.md` seeded; top risks need owners and issues.

## Scope
- Link top 5 risks to GitHub issues
- Mark status open/planned/partial honestly

## Akzeptanzkriterien
- [ ] R-001 through R-005 have linked issues or justified deferral
""",
    ),
    (
        "Reproduzierbaren Baseline-Start dokumentieren",
        "P1 – Reproducible Baseline Release",
        ["type:documentation", "area:infrastructure"],
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
    (
        "Laufzeit- und Abhängigkeitsversionen prüfen",
        "P1 – Reproducible Baseline Release",
        ["type:operations", "area:infrastructure"],
        """## Scope
- Pin/document Python 3.12, Node 22, dependency lock strategy

## Akzeptanzkriterien
- [ ] Versions recorded in baseline doc or tag notes
""",
    ),
    (
        "Bestehende Test- und CI-Abdeckung erfassen",
        "P1 – Reproducible Baseline Release",
        ["type:documentation", "area:governance"],
        """## Scope
- Document pytest markers, known failures, missing CI gap

## Akzeptanzkriterien
- [ ] Test commands in README/AGENTS accurate
- [ ] Known bulk postgres failures documented if still present
""",
    ),
    (
        "Reproduzierbaren Baseline-Release definieren",
        "P1 – Reproducible Baseline Release",
        ["type:feature", "area:governance"],
        """## Scope
- Define tag naming and exit criteria for baseline-paper-v*

## Akzeptanzkriterien
- [ ] Tag created on agreed commit
- [ ] CHANGELOG notes baseline
""",
    ),
    (
        "Backup- und Restore-Prozess prüfen",
        "P2 – Operational Reliability",
        ["type:operations", "area:infrastructure"],
        """## Scope
- Railway Postgres backup; restore drill once

## Akzeptanzkriterien
- [ ] Runbook section in `docs/runbooks/README.md` complete
- [ ] Restore tested on non-prod
""",
    ),
    (
        "Reconciliation-Anforderungen dokumentieren",
        "P2 – Operational Reliability",
        ["type:documentation", "area:accounting"],
        """## Scope
- Daily reconciliation checklist for paper soak

## Akzeptanzkriterien
- [ ] Procedure documented
- [ ] Owner and frequency defined
""",
    ),
    (
        "Idempotenz kritischer Verarbeitungspfade prüfen",
        "P2 – Operational Reliability",
        ["type:feature", "area:execution"],
        """## Scope
- Review fills, scheduler runs, portfolio snapshots for duplicate safety

## Akzeptanzkriterien
- [ ] Test coverage noted or gaps filed as bugs
""",
    ),
    (
        "Worker-Wiederanlauf nach Prozessabbruch testen",
        "P2 – Operational Reliability",
        ["type:operations", "area:execution"],
        """## Scope
- Kill worker mid-run; verify recovery and no duplicate entries

## Akzeptanzkriterien
- [ ] Test automated or runbook with recorded result
""",
    ),
    (
        "Incident- und Runbook-Lücken erfassen",
        "P2 – Operational Reliability",
        ["type:documentation", "area:governance"],
        """## Scope
- Complete TODO runbooks in `docs/runbooks/README.md`

## Akzeptanzkriterien
- [ ] Each critical op has issue or completed runbook
""",
    ),
    (
        "Kritische Betriebsmetriken definieren",
        "P2 – Operational Reliability",
        ["type:feature", "area:monitoring"],
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

    def log(self, msg: str) -> None:
        prefix = "[dry-run] " if self.dry_run else ""
        print(f"{prefix}{msg}")


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
        ctx.log(f"WARN: could not list labels: {result.stderr.strip()}")
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
            ctx.log(f"WARN: label create failed for '{name}': {result.stderr.strip()}")


def list_milestones(ctx: GhContext) -> dict[str, dict[str, Any]]:
    if not ctx.available or not ctx.authenticated:
        return {}
    # Use a stable JSON response to avoid CLI output variations.
    result = run_gh(["api", f"repos/{ctx.repo}/milestones?state=all&per_page=100"], check=False)
    if result.returncode != 0:
        ctx.log(f"WARN: could not list milestones: {result.stderr.strip()}")
        return {}
    try:
        items = json.loads(result.stdout or "[]")
    except json.JSONDecodeError:
        ctx.log("WARN: could not parse milestones JSON")
        return {}
    milestones: dict[str, dict[str, Any]] = {}
    if isinstance(items, list):
        for item in items:
            if isinstance(item, dict) and "title" in item:
                milestones[item["title"]] = item
    return milestones


def ensure_milestones(ctx: GhContext) -> dict[str, int]:
    existing = list_milestones(ctx)
    title_to_number: dict[str, int] = {t: m["number"] for t, m in existing.items()}
    for title, description in MILESTONES:
        if title in title_to_number:
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
            ctx.log(f"WARN: milestone create failed for '{title}': {result.stderr.strip()}")
            # If it already exists, we'll pick it up in the refresh below.
            continue
        try:
            created = json.loads(result.stdout)
        except json.JSONDecodeError:
            ctx.log(f"WARN: milestone create returned non-JSON for '{title}'")
            continue
        if isinstance(created, dict) and "number" in created:
            title_to_number[title] = created["number"]
    # refresh if we created any
    if not ctx.dry_run and ctx.authenticated:
        title_to_number.update({t: m["number"] for t, m in list_milestones(ctx).items()})
    return title_to_number


def list_issue_titles(ctx: GhContext) -> set[str]:
    if not ctx.available or not ctx.authenticated:
        return set()
    result = run_gh(
        ["issue", "list", "--repo", ctx.repo, "--state", "all", "--limit", "500", "--json", "title"],
        check=False,
    )
    if result.returncode != 0:
        ctx.log(f"WARN: could not list issues: {result.stderr.strip()}")
        return set()
    items = json.loads(result.stdout or "[]")
    return {item["title"] for item in items}


def ensure_seed_issues(ctx: GhContext, milestone_numbers: dict[str, int]) -> None:
    existing_titles = list_issue_titles(ctx)
    for title, milestone_title, labels, body in SEED_ISSUES:
        if title in existing_titles:
            ctx.log(f"issue exists: {title}")
            continue
        ctx.log(f"create issue: {title}")
        if ctx.dry_run or not ctx.authenticated:
            continue
        args = [
            "issue",
            "create",
            "--repo",
            ctx.repo,
            "--title",
            title,
            "--body",
            body,
        ]
        for label in labels:
            args.extend(["--label", label])
        ms_num = milestone_numbers.get(milestone_title)
        if ms_num is not None:
            args.extend(["--milestone", milestone_title])
        result = run_gh(args, check=False)
        if result.returncode != 0:
            ctx.log(f"WARN: issue create failed for '{title}': {result.stderr.strip()}")


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
        ctx.log(f"WARN: cannot list projects (need `project` scope?): {result.stderr.strip()}")
        ctx.log("Manual steps: see docs/PROJECT_OPERATING_SYSTEM.md")
        return
    try:
        projects = json.loads(result.stdout or "[]")
    except json.JSONDecodeError:
        projects = []
    if not isinstance(projects, list):
        ctx.log("WARN: unexpected projects JSON shape; skipping project automation")
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
        ctx.log(f"WARN: project create failed: {create.stderr.strip()}")
        ctx.log("Manual steps: see docs/PROJECT_OPERATING_SYSTEM.md")
        return
    ctx.log("project created — configure fields/views manually per docs/PROJECT_OPERATING_SYSTEM.md")


def build_context(dry_run: bool) -> GhContext:
    available = gh_available()
    authenticated = gh_authenticated() if available else False
    repo = detect_repo() if available and authenticated else ""
    if not repo and available:
        ctx = GhContext(available, authenticated, "", dry_run)
        ctx.log("WARN: could not detect repo — use dry-run preview only")
    return GhContext(available, authenticated, repo or "UNKNOWN/UNKNOWN", dry_run)


def main() -> int:
    parser = argparse.ArgumentParser(description="Setup GitHub labels, milestones, and seed issues")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--dry-run", action="store_true", help="Preview actions without writes")
    group.add_argument("--apply", action="store_true", help="Apply changes via gh")
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

    ensure_labels(ctx)
    milestone_numbers = ensure_milestones(ctx)
    ensure_seed_issues(ctx, milestone_numbers)
    try_create_project(ctx)

    print()
    if dry_run:
        print("Dry-run complete. Re-run with --apply after `gh auth login`.")
    elif not ctx.authenticated:
        print("Apply requested but gh not authenticated. No changes made.")
        return 1
    else:
        print("Apply complete.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
