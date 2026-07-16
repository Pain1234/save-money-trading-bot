<#
.SYNOPSIS
  Read-only Codex review gate for the current git worktree.

.DESCRIPTION
  Resolves merge-base vs BaseRef, writes a canonical UTF-8 (no BOM) diff,
  secret-scans, optionally invokes Codex (or uses a mock), validates schema 1.0,
  archives an immutable history copy, and exits with the gate codes.

.PARAMETER BaseRef
  Git ref used as the review base tip (default: origin/main). Merge-base with HEAD is used for the diff.

.PARAMETER HeadRef
  Optional head ref/SHA (default: current HEAD).

.PARAMETER SkipCodex
  Do not invoke the Codex CLI. Use with -MockResultPath for tests.

.PARAMETER MockResultPath
  Path to a simulated Codex JSON result (skips live Codex).

.PARAMETER RepoRoot
  Optional explicit repo root. Default: git rev-parse --show-toplevel.

.PARAMETER DiffFile
  Optional precomputed patch path (tests). Skips git diff generation.

.PARAMETER AllowEmptyDiff
  Tests only: allow empty diffs. Default fails empty diffs as REVIEW_FAILED.

.PARAMETER PreserveMockRefs
  When using -MockResultPath, do not overlay reviewed_base/head/diff_hash
  (for stale-head / wrong-hash tests).

.NOTES
  Exit codes: 0 APPROVED, 2 CHANGES_REQUIRED, 3 REVIEW_FAILED, 4 stale/wrong.
#>
[CmdletBinding()]
param(
    [string]$BaseRef = "origin/main",
    [string]$HeadRef = "",
    [switch]$SkipCodex,
    [string]$MockResultPath = "",
    [string]$RepoRoot = "",
    [string]$DiffFile = "",
    [switch]$AllowEmptyDiff,
    [switch]$PreserveMockRefs
)

Set-StrictMode -Version Latest
# Prefer Stop for unexpected errors; REVIEW_FAILED paths set exit codes explicitly.
$ErrorActionPreference = "Stop"

$Script:AgentLoopDir = $PSScriptRoot
$Script:ExitApproved = 0
$Script:ExitChangesRequired = 2
$Script:ExitReviewFailed = 3
$Script:ExitStale = 4

function Write-ReviewFailedResult {
    param(
        [Parameter(Mandatory = $true)][string]$ResultPath,
        [Parameter(Mandatory = $true)][string]$Summary,
        [string]$ReviewedBase = "unknown",
        [string]$ReviewedHead = "unknown",
        [string]$ReviewedDiffHash = "unknown",
        [string[]]$ReviewNotes = @()
    )
    $payload = [ordered]@{
        schema_version      = "1.0"
        verdict             = "REVIEW_FAILED"
        reviewed_base       = $ReviewedBase
        reviewed_head       = $ReviewedHead
        reviewed_diff_hash  = $ReviewedDiffHash
        summary             = $Summary
        findings            = @()
        required_tests      = @()
        review_notes        = @($ReviewNotes)
    }
    $json = ($payload | ConvertTo-Json -Depth 8)
    # UTF-8 no BOM
    $utf8 = New-Object System.Text.UTF8Encoding $false
    [System.IO.File]::WriteAllText($ResultPath, $json + "`n", $utf8)
}

function Get-Sha256NoBom {
    param([Parameter(Mandatory = $true)][string]$Path)
    $py = @"
from pathlib import Path
import hashlib
import sys
p = Path(sys.argv[1])
raw = p.read_bytes()
if raw.startswith(b'\xef\xbb\xbf'):
    raw = raw[3:]
print(hashlib.sha256(raw).hexdigest())
"@
    $out = & python -c $py $Path
    if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($out)) {
        throw "Failed to compute SHA256 for $Path"
    }
    return $out.Trim()
}

function Resolve-RepoRoot {
    param([string]$Explicit)
    if (-not [string]::IsNullOrWhiteSpace($Explicit)) {
        $resolved = (Resolve-Path -LiteralPath $Explicit).Path
        return $resolved
    }
    $top = & git rev-parse --show-toplevel 2>$null
    if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($top)) {
        throw "Unable to resolve git toplevel (run inside a git worktree or pass -RepoRoot)."
    }
    return $top.Trim()
}

function Test-CodexAvailable {
    try {
        $null = Get-Command codex -ErrorAction Stop
        return $true
    }
    catch {
        return $false
    }
}

function Overlay-MockRefsIfNeeded {
    param(
        [Parameter(Mandatory = $true)][hashtable]$Data,
        [Parameter(Mandatory = $true)][string]$BaseSha,
        [Parameter(Mandatory = $true)][string]$HeadSha,
        [Parameter(Mandatory = $true)][string]$DiffHash,
        [switch]$Preserve
    )
    # Default overlay when mock is used unless -PreserveMockRefs.
    # Placeholders like WILL_BE_SET are always replaced when not preserving.
    # AGENT_LOOP_OVERLAY_REFS=0 disables default overlay (except placeholders).
    if ($Preserve) {
        return $Data
    }
    $overlayEnv = $env:AGENT_LOOP_OVERLAY_REFS
    $placeholders = @("WILL_BE_SET", "PLACEHOLDER", "TBD")
    $hasPlaceholder = $false
    foreach ($key in @("reviewed_base", "reviewed_head", "reviewed_diff_hash")) {
        $val = [string]$Data[$key]
        if ($placeholders -contains $val -or $val -like "WILL_BE_SET*") {
            $hasPlaceholder = $true
            break
        }
    }
    $defaultOverlay = ($overlayEnv -ne "0")
    if ($defaultOverlay -or $hasPlaceholder -or $overlayEnv -eq "1") {
        $Data["reviewed_base"] = $BaseSha
        $Data["reviewed_head"] = $HeadSha
        $Data["reviewed_diff_hash"] = $DiffHash
    }
    return $Data
}

function ConvertTo-HashtableFromJson {
    param([Parameter(Mandatory = $true)][string]$JsonText)
    $obj = $JsonText | ConvertFrom-Json
    return ConvertTo-HashtableRecursive $obj
}

function ConvertTo-HashtableRecursive {
    param($InputObject)
    if ($null -eq $InputObject) { return $null }
    # IDictionary/Hashtable before IEnumerable: hashtables enumerate as keys otherwise.
    if ($InputObject -is [System.Collections.IDictionary]) {
        $ht = [ordered]@{}
        foreach ($key in @($InputObject.Keys)) {
            $ht[$key] = ConvertTo-HashtableRecursive $InputObject[$key]
        }
        return $ht
    }
    if ($InputObject -is [System.Collections.IEnumerable] -and
        -not ($InputObject -is [string])) {
        $list = @()
        foreach ($item in $InputObject) {
            $list += ,(ConvertTo-HashtableRecursive $item)
        }
        return $list
    }
    if ($InputObject.PSObject -and $InputObject.PSObject.Properties -and
        -not ($InputObject -is [string]) -and
        -not ($InputObject -is [ValueType])) {
        # Treat PSCustomObject as map
        if ($InputObject -is [pscustomobject]) {
            $ht = [ordered]@{}
            foreach ($prop in $InputObject.PSObject.Properties) {
                $ht[$prop.Name] = ConvertTo-HashtableRecursive $prop.Value
            }
            return $ht
        }
    }
    return $InputObject
}

function Write-JsonFile {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)]$Data
    )
    $json = ($Data | ConvertTo-Json -Depth 20)
    $utf8 = New-Object System.Text.UTF8Encoding $false
    [System.IO.File]::WriteAllText($Path, $json + "`n", $utf8)
}

# --- main ---
$resultPath = Join-Path $Script:AgentLoopDir "codex-review-result.json"
$schemaPath = Join-Path $Script:AgentLoopDir "codex-review-schema.json"
$promptPath = Join-Path $Script:AgentLoopDir "codex-review-prompt.md"
$historyDir = Join-Path $Script:AgentLoopDir "review-history"
$tmpDir = Join-Path $Script:AgentLoopDir "tmp"
$inputSummaryPath = Join-Path $Script:AgentLoopDir "current-review-input.txt"

$reviewedBase = "unknown"
$reviewedHead = "unknown"
$diffHash = "unknown"
$diffPath = ""

try {
    New-Item -ItemType Directory -Force -Path $tmpDir | Out-Null
    New-Item -ItemType Directory -Force -Path $historyDir | Out-Null

    $root = Resolve-RepoRoot -Explicit $RepoRoot
    Set-Location -LiteralPath $root

    # Git state
    $dirty = & git status --porcelain 2>$null
    if ($LASTEXITCODE -eq 0 -and -not [string]::IsNullOrWhiteSpace($dirty)) {
        Write-Warning "Working tree is dirty; review uses committed HEAD (or -HeadRef) only."
    }

    if ([string]::IsNullOrWhiteSpace($HeadRef)) {
        $reviewedHead = (& git rev-parse HEAD 2>$null)
        if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($reviewedHead)) {
            throw "Cannot determine HEAD SHA."
        }
        $reviewedHead = $reviewedHead.Trim()
    }
    else {
        $reviewedHead = (& git rev-parse $HeadRef 2>$null)
        if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($reviewedHead)) {
            throw "Cannot resolve -HeadRef '$HeadRef'."
        }
        $reviewedHead = $reviewedHead.Trim()
    }

    $baseResolved = (& git rev-parse $BaseRef 2>$null)
    if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($baseResolved)) {
        throw "Cannot resolve -BaseRef '$BaseRef'."
    }
    $baseResolved = $baseResolved.Trim()

    $mergeBase = (& git merge-base $BaseRef $reviewedHead 2>$null)
    if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($mergeBase)) {
        throw "Cannot compute merge-base of '$BaseRef' and '$reviewedHead'."
    }
    $reviewedBase = $mergeBase.Trim()

    $diffPath = Join-Path $tmpDir "current-diff.patch"
    if (-not [string]::IsNullOrWhiteSpace($DiffFile)) {
        $srcDiff = (Resolve-Path -LiteralPath $DiffFile).Path
        # Copy as UTF-8 no BOM bytes (strip BOM if present)
        $raw = [System.IO.File]::ReadAllBytes($srcDiff)
        if ($raw.Length -ge 3 -and $raw[0] -eq 0xEF -and $raw[1] -eq 0xBB -and $raw[2] -eq 0xBF) {
            $raw = $raw[3..($raw.Length - 1)]
        }
        [System.IO.File]::WriteAllBytes($diffPath, $raw)
    }
    else {
        $diffText = & git diff --no-ext-diff "$reviewedBase...$reviewedHead"
        if ($null -eq $diffText) { $diffText = "" }
        if ($diffText -is [System.Array]) {
            $diffText = ($diffText -join "`n")
        }
        # Normalize to LF UTF-8 no BOM for stable hashing
        $diffText = [string]$diffText
        if ($diffText.Length -gt 0 -and -not $diffText.EndsWith("`n")) {
            $diffText = $diffText + "`n"
        }
        $utf8 = New-Object System.Text.UTF8Encoding $false
        [System.IO.File]::WriteAllText($diffPath, $diffText.Replace("`r`n", "`n").Replace("`r", "`n"), $utf8)
    }

    $diffHash = Get-Sha256NoBom -Path $diffPath
    $diffBytes = [System.IO.File]::ReadAllBytes($diffPath)
    $diffIsEmpty = ($diffBytes.Length -eq 0) -or (
        ([System.Text.Encoding]::UTF8.GetString($diffBytes).Trim().Length -eq 0)
    )

    $useMock = -not [string]::IsNullOrWhiteSpace($MockResultPath)
    $shortSha = $reviewedHead.Substring(0, [Math]::Min(12, $reviewedHead.Length))

    # Input summary (gitignored)
    $summaryLines = @(
        "reviewed_base=$reviewedBase"
        "reviewed_head=$reviewedHead"
        "reviewed_diff_hash=$diffHash"
        "base_ref=$BaseRef"
        "diff_path=$diffPath"
        "mock=$useMock"
    )
    $utf8 = New-Object System.Text.UTF8Encoding $false
    [System.IO.File]::WriteAllText($inputSummaryPath, ($summaryLines -join "`n") + "`n", $utf8)

    if ($diffIsEmpty -and -not $AllowEmptyDiff) {
        # Allow mock empty-diff path when explicitly testing with AllowEmptyDiff only;
        # default: fail.
        Write-ReviewFailedResult -ResultPath $resultPath -Summary "Empty diff versus merge-base; nothing to review." `
            -ReviewedBase $reviewedBase -ReviewedHead $reviewedHead -ReviewedDiffHash $diffHash `
            -ReviewNotes @("Empty diff for $reviewedBase...$reviewedHead")
        Write-Host "REVIEW_FAILED: empty diff (use -AllowEmptyDiff only in tests)."
        exit $Script:ExitReviewFailed
    }

    # Secret scan ? never call Codex on failure
    $scanScript = Join-Path $Script:AgentLoopDir "secret_scan.py"
    & python $scanScript --diff $diffPath
    $scanCode = $LASTEXITCODE
    if ($scanCode -eq 1) {
        Write-ReviewFailedResult -ResultPath $resultPath `
            -Summary "Secret-like patterns found in diff; refusing to invoke Codex." `
            -ReviewedBase $reviewedBase -ReviewedHead $reviewedHead -ReviewedDiffHash $diffHash `
            -ReviewNotes @("secret_scan.py exited 1", "Fix or remove secrets from the diff and re-run.")
        Write-Host "REVIEW_FAILED: secrets detected in diff. Codex was not called."
        exit $Script:ExitReviewFailed
    }
    if ($scanCode -ne 0) {
        Write-ReviewFailedResult -ResultPath $resultPath `
            -Summary "Secret scan failed with I/O or usage error (exit $scanCode)." `
            -ReviewedBase $reviewedBase -ReviewedHead $reviewedHead -ReviewedDiffHash $diffHash
        Write-Host "REVIEW_FAILED: secret_scan exit $scanCode"
        exit $Script:ExitReviewFailed
    }

    # Obtain review result JSON
    if ($useMock -or ($SkipCodex -and $useMock)) {
        if (-not (Test-Path -LiteralPath $MockResultPath)) {
            throw "MockResultPath not found: $MockResultPath"
        }
        # Round-trip mock JSON via Python so single-element arrays are not collapsed
        # (Windows PowerShell ConvertFrom-Json / ConvertTo-Json unwraps length-1 arrays).
        $mockResolved = (Resolve-Path -LiteralPath $MockResultPath).Path
        $preserveFlag = if ($PreserveMockRefs) { "1" } else { "0" }
        $overlayEnv = if ($null -ne $env:AGENT_LOOP_OVERLAY_REFS) { [string]$env:AGENT_LOOP_OVERLAY_REFS } else { "" }
        # Empty string args are dropped by PowerShell; use sentinel for default overlay env.
        if ([string]::IsNullOrEmpty($overlayEnv)) { $overlayEnv = "__DEFAULT__" }
        $applyMock = Join-Path $Script:AgentLoopDir "apply_mock_result.py"
        & python $applyMock $mockResolved $resultPath $reviewedBase $reviewedHead $diffHash $preserveFlag $overlayEnv
        if ($LASTEXITCODE -ne 0) {
            throw "Failed to apply mock result from $MockResultPath"
        }
    }
    elseif ($SkipCodex -and -not $useMock) {
        Write-ReviewFailedResult -ResultPath $resultPath `
            -Summary "SkipCodex set without MockResultPath; cannot produce a review result." `
            -ReviewedBase $reviewedBase -ReviewedHead $reviewedHead -ReviewedDiffHash $diffHash
        Write-Host "REVIEW_FAILED: -SkipCodex requires -MockResultPath"
        exit $Script:ExitReviewFailed
    }
    else {
        if (-not (Test-CodexAvailable)) {
            Write-ReviewFailedResult -ResultPath $resultPath `
                -Summary "Codex CLI not available and no -MockResultPath provided." `
                -ReviewedBase $reviewedBase -ReviewedHead $reviewedHead -ReviewedDiffHash $diffHash `
                -ReviewNotes @("Install Codex CLI or pass -MockResultPath for tests.")
            Write-Host "REVIEW_FAILED: Codex CLI missing."
            exit $Script:ExitReviewFailed
        }

        # Build instruction file under tmp (outside long-lived tracked paths)
        $instructionPath = Join-Path $tmpDir "codex-instruction.txt"
        $codexOutPath = Join-Path $tmpDir "codex-stdout.json"
        $instruction = @"
Read-only review. Do not write files into the repository tree.

Follow the prompt file exactly:
$promptPath

Review this git diff patch (source of truth):
$diffPath

Output MUST be a single JSON object matching schema:
$schemaPath

Use these ref values exactly:
reviewed_base=$reviewedBase
reviewed_head=$reviewedHead
reviewed_diff_hash=$diffHash

Review input summary:
$inputSummaryPath
"@
        $utf8 = New-Object System.Text.UTF8Encoding $false
        [System.IO.File]::WriteAllText($instructionPath, $instruction, $utf8)

        # Prefer read-only exec; never use write-to-repo modes.
        # Capture stdout to a temp file under .agent-loop/tmp (gitignored).
        $prevEap = $ErrorActionPreference
        $ErrorActionPreference = "Continue"
        & codex exec --skip-git-repo-check $instructionPath 2>&1 | Tee-Object -FilePath $codexOutPath | Out-Null
        $codexExit = $LASTEXITCODE
        $ErrorActionPreference = $prevEap

        if ($codexExit -ne 0) {
            Write-ReviewFailedResult -ResultPath $resultPath `
                -Summary "Codex exec failed with exit code $codexExit." `
                -ReviewedBase $reviewedBase -ReviewedHead $reviewedHead -ReviewedDiffHash $diffHash `
                -ReviewNotes @("See $codexOutPath for Codex output")
            Write-Host "REVIEW_FAILED: codex exec exit $codexExit"
            exit $Script:ExitReviewFailed
        }

        $rawOut = [System.IO.File]::ReadAllText($codexOutPath)
        # Extract JSON object from stdout (first { ... last })
        $start = $rawOut.IndexOf("{")
        $end = $rawOut.LastIndexOf("}")
        if ($start -lt 0 -or $end -le $start) {
            Write-ReviewFailedResult -ResultPath $resultPath `
                -Summary "Codex stdout did not contain a JSON object." `
                -ReviewedBase $reviewedBase -ReviewedHead $reviewedHead -ReviewedDiffHash $diffHash
            Write-Host "REVIEW_FAILED: no JSON in Codex output"
            exit $Script:ExitReviewFailed
        }
        $jsonSlice = $rawOut.Substring($start, $end - $start + 1)
        # Validate it parses; rewrite canonical file
        $null = $jsonSlice | ConvertFrom-Json
        $utf8 = New-Object System.Text.UTF8Encoding $false
        [System.IO.File]::WriteAllText($resultPath, $jsonSlice.Trim() + "`n", $utf8)
    }

    # Validate
    $validateScript = Join-Path $Script:AgentLoopDir "validate-review-result.py"
    & python $validateScript `
        --result $resultPath `
        --schema $schemaPath `
        --expected-head $reviewedHead `
        --expected-base $reviewedBase `
        --expected-diff-hash $diffHash
    $valCode = $LASTEXITCODE
    if ($valCode -eq 4) {
        Write-Host "STALE/WRONG review refs (validate exit 4)."
        exit $Script:ExitStale
    }
    if ($valCode -ne 0) {
        # Treat schema/verdict/usage failures as REVIEW_FAILED gate outcome
        Write-Warning "Validation failed (exit $valCode); rewriting REVIEW_FAILED result."
        Write-ReviewFailedResult -ResultPath $resultPath `
            -Summary "Review result failed validation (validate-review-result.py exit $valCode)." `
            -ReviewedBase $reviewedBase -ReviewedHead $reviewedHead -ReviewedDiffHash $diffHash `
            -ReviewNotes @("Original result rejected by validator", "exit=$valCode")
        exit $Script:ExitReviewFailed
    }

    # History copy
    $stamp = [DateTime]::UtcNow.ToString("yyyyMMddTHHmmssZ")
    $histName = "${stamp}_${shortSha}.json"
    $histPath = Join-Path $historyDir $histName
    Copy-Item -LiteralPath $resultPath -Destination $histPath -Force

    $verdictObj = Get-Content -LiteralPath $resultPath -Raw | ConvertFrom-Json
    $verdict = [string]$verdictObj.verdict
    Write-Host "Codex review gate: $verdict (history: $histName)"
    switch ($verdict) {
        "APPROVED" { exit $Script:ExitApproved }
        "CHANGES_REQUIRED" { exit $Script:ExitChangesRequired }
        "REVIEW_FAILED" { exit $Script:ExitReviewFailed }
        default {
            Write-Host "Unexpected verdict: $verdict"
            exit $Script:ExitReviewFailed
        }
    }
}
catch {
    $msg = $_.Exception.Message
    try {
        Write-ReviewFailedResult -ResultPath $resultPath -Summary "Review gate error: $msg" `
            -ReviewedBase $reviewedBase -ReviewedHead $reviewedHead -ReviewedDiffHash $diffHash `
            -ReviewNotes @($msg)
    }
    catch {
        Write-Warning "Could not write REVIEW_FAILED result: $($_.Exception.Message)"
    }
    Write-Host "REVIEW_FAILED: $msg"
    exit $Script:ExitReviewFailed
}
