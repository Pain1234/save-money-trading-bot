# Creates six issue-scoped branches from current working-tree P2 artifacts.
# Prerequisites: run from repo root on main; P2 files present (see docs/P2-PR-SPLIT.md).
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $root

$artifactRoot = $root
if (-not (Test-Path "$artifactRoot\docs\operations\metrics.md")) {
    throw "Missing docs/operations/metrics.md - apply P2 changes before splitting."
}

function Write-ChangelogFromMain {
    param([string[]]$Added, [string[]]$Changed)
    git show main:CHANGELOG.md | Set-Content CHANGELOG.md -Encoding utf8
    $text = Get-Content CHANGELOG.md -Raw
    if ($Added -and $Added.Count -gt 0) {
        $block = "### Added`r`n`r`n" + ($Added -join "`r`n") + "`r`n`r`n"
        $text = $text -replace "## \[Unreleased\]\r?\n\r?\n### Changed", "## [Unreleased]`r`n`r`n$block### Changed"
    }
    if ($Changed -and $Changed.Count -gt 0) {
        $insert = ($Changed -join "`r`n") + "`r`n"
        $text = $text -replace "(### Changed\r?\n\r?\n)", "`$1$insert"
    }
    [IO.File]::WriteAllText("$root\CHANGELOG.md", $text.TrimEnd() + "`n")
}

function Commit-Branch {
    param([string]$Branch, [string[]]$Added, [string[]]$Changed, [string[]]$Paths, [string]$Message)
    git checkout main | Out-Null
    git checkout -B $Branch | Out-Null
    Write-ChangelogFromMain -Added $Added -Changed $Changed
    git add @Paths CHANGELOG.md
    git diff --cached --check
    git commit -m $Message
    Write-Host "Created $Branch"
}

Commit-Branch "p2/16-metrics" @(
    '- `docs/operations/metrics.md` - critical operational metrics catalog (Issue #16).'
) @() @("docs/operations/metrics.md") "docs: add operational metrics catalog (Issue #16)"

Commit-Branch "p2/13-idempotency-audit" @(
    '- `docs/operations/idempotency-audit.md` - idempotency path inventory (Issue #13).'
) @() @("docs/operations/idempotency-audit.md") "docs: add idempotency audit (Issue #13)"

Commit-Branch "p2/14-worker-restart" @(
    '- `docs/runbooks/worker-restart.md` - worker restart runbook (Issue #14).'
) @() @("docs/runbooks/worker-restart.md") "docs: add worker restart runbook (Issue #14)"

Commit-Branch "p2/12-reconciliation" @(
    '- `scripts/reconcile_accounting.py` - wallet reconciliation CLI (Issue #12).',
    '- `tests/scripts/test_reconcile_accounting.py` - exit code and cleanup tests.'
) @(
    '- `docs/runbooks/reconciliation-daily.md` - weekly reconciliation procedure (Issue #12).'
) @(
    "docs/runbooks/reconciliation-daily.md",
    "scripts/reconcile_accounting.py",
    "tests/scripts/test_reconcile_accounting.py"
) "docs: add reconciliation runbook and script (Issue #12)"

# #11: backup draft + minimal R-009 update
git checkout main | Out-Null
git checkout -B p2/11-backup-restore-draft | Out-Null
git show main:docs/RISK_REGISTER.md | Set-Content docs/RISK_REGISTER.md -Encoding utf8
$risk = Get-Content docs/RISK_REGISTER.md -Raw
$risk = $risk.Replace(
    '| R-009 | PostgreSQL data loss without tested backup | Infrastruktur | Low | Critical | Critical | Backup age monitoring | P2 backup/restore runbook and test | infrastructure | open | — |',
    '| R-009 | PostgreSQL data loss without tested backup | Infrastruktur | Low | Critical | Critical | Backup age monitoring | [`docs/runbooks/backup-restore.md`](runbooks/backup-restore.md) - draft; restore drill not executed | infrastructure | open | [#11](https://github.com/Pain1234/save-money-trading-bot/issues/11) |'
)
Set-Content docs/RISK_REGISTER.md $risk.TrimEnd()
Write-ChangelogFromMain @(
    '- `docs/runbooks/backup-restore.md` - backup/restore runbook draft (Issue #11; drill pending).'
) @(
    '- `docs/RISK_REGISTER.md` - R-009 links draft runbook; remains open until drill.'
)
git add docs/runbooks/backup-restore.md docs/RISK_REGISTER.md CHANGELOG.md
git diff --cached --check
git commit -m "docs: add backup-restore runbook draft (Issue #11)"

# #15: index + bundled runbooks + governance
git checkout main | Out-Null
git checkout -B p2/15-runbooks-index | Out-Null
git show main:CHANGELOG.md | Set-Content CHANGELOG.md -Encoding utf8
$cl = Get-Content CHANGELOG.md -Raw
$note = @"

### Added

- P2 runbooks: deployment-verify, worker-safe-stop, kill-switch (Issue #15).
- Tabletop incident docs/incidents/INC-20260714-001-tabletop-duplicate-fill.md.

### Changed

- docs/runbooks/README.md - runbook index; partial kill-switch and backup-restore.
- ROADMAP.md - P2 exit criteria honest (not complete).
- docs/RISK_REGISTER.md - R-006/R-007 linked to P2 artifacts.

### Note

- Issue #15 bundles three runbooks; see docs/P2-PR-SPLIT.md for deviation rationale.
- P2 not exit-complete until Issue #11 restore drill done.

"@
$cl = $cl -replace "## \[Unreleased\]\r?\n\r?\n### Changed", "## [Unreleased]$note### Changed"
Set-Content CHANGELOG.md $cl.TrimEnd()
git add docs/runbooks/README.md docs/runbooks/deployment-verify.md docs/runbooks/worker-safe-stop.md docs/runbooks/kill-switch.md docs/incidents/ ROADMAP.md docs/RISK_REGISTER.md CHANGELOG.md docs/P2-PR-SPLIT.md
git diff --cached --check
git commit -m "docs: P2 runbook index, ops runbooks, tabletop (Issue #15)"

git branch --list "p2/*"
Write-Host "Done. Push branches and open PRs per docs/P2-PR-SPLIT.md"
