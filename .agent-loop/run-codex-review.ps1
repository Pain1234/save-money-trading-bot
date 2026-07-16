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

.PARAMETER CodexBin
  Optional path/name of the Codex executable (tests: fake recorder).
  Overrides env AGENT_LOOP_CODEX_BIN when set.

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
    [switch]$PreserveMockRefs,
    [string]$CodexBin = ""
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

function Resolve-BaseRefOrFallback {
    <#
    .SYNOPSIS
      Resolve a usable base git ref for merge-base / reviewed_base.
    .DESCRIPTION
      Tries the explicit -BaseRef first, then origin/main, main, master.
      Returns a hashtable: Resolved (bool), Ref, Sha, Tried (string[]).
      When nothing resolves, Resolved=$false (caller may use DiffFile offline mode).
    #>
    param([Parameter(Mandatory = $true)][string]$Preferred)
    $candidates = [System.Collections.Generic.List[string]]::new()
    if (-not [string]::IsNullOrWhiteSpace($Preferred)) {
        $candidates.Add($Preferred.Trim()) | Out-Null
    }
    foreach ($c in @("origin/main", "main", "master")) {
        # Tests may set AGENT_LOOP_BASE_REF_ONLY=1 to skip fallbacks and exercise DiffFile offline mode.
        if ($env:AGENT_LOOP_BASE_REF_ONLY -eq "1") {
            break
        }
        if ($candidates -notcontains $c) {
            $candidates.Add($c) | Out-Null
        }
    }
    $tried = [System.Collections.Generic.List[string]]::new()
    $prevEap = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        foreach ($ref in $candidates) {
            $tried.Add($ref) | Out-Null
            # Native git may write "fatal:" to stderr; do not let that abort fallbacks.
            $resolved = & git rev-parse $ref 2>$null
            if ($LASTEXITCODE -eq 0 -and -not [string]::IsNullOrWhiteSpace($resolved)) {
                return @{
                    Resolved = $true
                    Ref      = $ref
                    Sha      = $resolved.Trim()
                    Tried    = @($tried)
                }
            }
        }
    }
    finally {
        $ErrorActionPreference = $prevEap
    }
    return @{
        Resolved = $false
        Ref      = $Preferred
        Sha      = $null
        Tried    = @($tried)
    }
}

function Resolve-CodexBin {
    param([string]$Explicit)
    if (-not [string]::IsNullOrWhiteSpace($Explicit)) {
        return $Explicit.Trim()
    }
    if (-not [string]::IsNullOrWhiteSpace($env:AGENT_LOOP_CODEX_BIN)) {
        return $env:AGENT_LOOP_CODEX_BIN.Trim()
    }
    return "codex"
}

function Test-CodexAvailable {
    param([Parameter(Mandatory = $true)][string]$Bin)
    if ($Bin -ne "codex" -and (Test-Path -LiteralPath $Bin)) {
        return $true
    }
    try {
        $null = Get-Command $Bin -ErrorAction Stop
        return $true
    }
    catch {
        return $false
    }
}

function Invoke-CodexCommand {
    param(
        [Parameter(Mandatory = $true)][string]$Bin,
        [Parameter(Mandatory = $true)][string[]]$ArgumentList
    )
    if ($Bin -match '\.py$') {
        & python $Bin @ArgumentList
    }
    else {
        & $Bin @ArgumentList
    }
}

function Get-CodexExecHelpText {
    param([Parameter(Mandatory = $true)][string]$Bin)
    $prevEap = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    $helpOut = Invoke-CodexCommand -Bin $Bin -ArgumentList @("exec", "--help") 2>&1 | Out-String
    $ErrorActionPreference = $prevEap
    return $helpOut
}

function New-CodexExecArgumentList {
    param(
        [Parameter(Mandatory = $true)][string]$Bin,
        [Parameter(Mandatory = $true)][string]$InstructionPath
    )
    $helpText = Get-CodexExecHelpText -Bin $Bin
    $required = @(
        @{ Flag = "--sandbox"; Label = "sandbox" },
        @{ Flag = "--ask-for-approval"; Label = "ask-for-approval" },
        @{ Flag = "--ignore-user-config"; Label = "ignore-user-config" }
    )
    foreach ($req in $required) {
        if ($helpText -notmatch [regex]::Escape($req.Flag)) {
            throw ("Codex CLI does not advertise required read-only flag '{0}'. " +
                "Cannot enforce sandbox; refusing to run review.") -f $req.Flag
        }
    }

    $argList = [System.Collections.Generic.List[string]]::new()
    $argList.Add("exec") | Out-Null
    $argList.Add("--skip-git-repo-check") | Out-Null
    $argList.Add("--sandbox") | Out-Null
    $argList.Add("read-only") | Out-Null
    $argList.Add("--ask-for-approval") | Out-Null
    $argList.Add("never") | Out-Null
    $argList.Add("--ignore-user-config") | Out-Null
    if ($helpText -match "--ignore-rules") {
        $argList.Add("--ignore-rules") | Out-Null
    }
    if ($helpText -match "--ephemeral") {
        $argList.Add("--ephemeral") | Out-Null
    }
    $argList.Add($InstructionPath) | Out-Null
    return , $argList.ToArray()
}

function Get-UniqueHistoryPath {
    param(
        [Parameter(Mandatory = $true)][string]$HistoryDir,
        [Parameter(Mandatory = $true)][string]$ShortSha
    )
    $stamp = [DateTime]::UtcNow.ToString("yyyyMMddTHHmmssfffZ")
    $baseName = "${stamp}_${ShortSha}.json"
    $candidate = Join-Path $HistoryDir $baseName
    if (-not (Test-Path -LiteralPath $candidate)) {
        return $candidate
    }
    $n = 1
    while ($true) {
        $alt = Join-Path $HistoryDir ("${stamp}_${ShortSha}_${n}.json")
        if (-not (Test-Path -LiteralPath $alt)) {
            return $alt
        }
        $n++
        if ($n -gt 1000) {
            throw "Unable to allocate unique history filename under $HistoryDir"
        }
    }
}

function Assert-PostCodexHeadFresh {
    param(
        [Parameter(Mandatory = $true)][string]$ReviewedHead,
        [Parameter(Mandatory = $true)][string]$ReviewedBase,
        [Parameter(Mandatory = $true)][string]$DiffHash,
        [Parameter(Mandatory = $true)][string]$DiffPath,
        [string]$HeadRefParam = "",
        [string]$DiffFileParam = ""
    )
    # Test override: force a post-Codex HEAD mismatch without rewriting git state.
    if (-not [string]::IsNullOrWhiteSpace($env:AGENT_LOOP_POST_CODEX_HEAD)) {
        $currentHead = $env:AGENT_LOOP_POST_CODEX_HEAD.Trim()
    }
    elseif ([string]::IsNullOrWhiteSpace($HeadRefParam)) {
        $currentHead = (& git rev-parse HEAD 2>$null)
        if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($currentHead)) {
            throw "Post-Codex HEAD recheck failed: cannot read HEAD."
        }
        $currentHead = $currentHead.Trim()
    }
    else {
        $currentHead = (& git rev-parse $HeadRefParam 2>$null)
        if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($currentHead)) {
            throw "Post-Codex HEAD recheck failed: cannot resolve -HeadRef."
        }
        $currentHead = $currentHead.Trim()
    }

    if ($currentHead -ne $ReviewedHead) {
        Write-Host "STALE: HEAD changed during review ($ReviewedHead -> $currentHead)."
        exit $Script:ExitStale
    }

    # Recompute diff hash when using live git diff (not a frozen -DiffFile).
    if ([string]::IsNullOrWhiteSpace($DiffFileParam)) {
        $reMerge = (& git merge-base $ReviewedBase $currentHead 2>$null)
        if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($reMerge)) {
            throw "Post-Codex recheck: cannot recompute merge-base."
        }
        $reDiffText = & git diff --no-ext-diff "$($reMerge.Trim())...$currentHead"
        if ($null -eq $reDiffText) { $reDiffText = "" }
        if ($reDiffText -is [System.Array]) {
            $reDiffText = ($reDiffText -join "`n")
        }
        $reDiffText = [string]$reDiffText
        if ($reDiffText.Length -gt 0 -and -not $reDiffText.EndsWith("`n")) {
            $reDiffText = $reDiffText + "`n"
        }
        $utf8 = New-Object System.Text.UTF8Encoding $false
        $rePath = Join-Path (Join-Path $Script:AgentLoopDir "tmp") "post-codex-recheck.patch"
        [System.IO.File]::WriteAllText(
            $rePath,
            $reDiffText.Replace("`r`n", "`n").Replace("`r", "`n"),
            $utf8
        )
        $reHash = Get-Sha256NoBom -Path $rePath
        if ($reHash -ne $DiffHash) {
            Write-Host "STALE: diff hash changed during review."
            exit $Script:ExitStale
        }
    }
    else {
        $reHash = Get-Sha256NoBom -Path $DiffPath
        if ($reHash -ne $DiffHash) {
            Write-Host "STALE: diff hash changed during review."
            exit $Script:ExitStale
        }
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

    $baseInfo = Resolve-BaseRefOrFallback -Preferred $BaseRef
    $hasDiffFile = -not [string]::IsNullOrWhiteSpace($DiffFile)

    if (-not $baseInfo.Resolved) {
        if ($hasDiffFile) {
            # Documented test/offline mode: shallow CI or missing base refs with -DiffFile.
            # Skip merge-base; set reviewed_base = reviewed_head and continue with DiffFile bytes.
            $offlineMsg = ("BaseRef could not be resolved (tried: {0}). " +
                "-DiffFile offline mode: reviewed_base=reviewed_head.") -f ($baseInfo.Tried -join ", ")
            Write-Warning $offlineMsg
            $reviewedBase = $reviewedHead
            $BaseRef = "(diff-file-offline)"
        }
        else {
            throw ("Cannot resolve -BaseRef. Tried: {0}. " +
                "Fetch origin/main (or pass -BaseRef / use -DiffFile for offline tests).") -f (
                $baseInfo.Tried -join ", ")
        }
    }
    else {
        $BaseRef = $baseInfo.Ref
        $mergeBase = (& git merge-base $baseInfo.Ref $reviewedHead 2>$null)
        if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($mergeBase)) {
            if ($hasDiffFile) {
                $mbMsg = ("Cannot compute merge-base of '{0}' and '{1}'. " +
                    "-DiffFile offline mode: reviewed_base=reviewed_head.") -f $baseInfo.Ref, $reviewedHead
                Write-Warning $mbMsg
                $reviewedBase = $reviewedHead
                $BaseRef = "(diff-file-offline)"
            }
            else {
                throw "Cannot compute merge-base of '$($baseInfo.Ref)' and '$reviewedHead'."
            }
        }
        else {
            $reviewedBase = $mergeBase.Trim()
        }
    }

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
        $resolvedCodexBin = Resolve-CodexBin -Explicit $CodexBin
        if (-not (Test-CodexAvailable -Bin $resolvedCodexBin)) {
            Write-ReviewFailedResult -ResultPath $resultPath `
                -Summary "Codex CLI not available and no -MockResultPath provided." `
                -ReviewedBase $reviewedBase -ReviewedHead $reviewedHead -ReviewedDiffHash $diffHash `
                -ReviewNotes @("Install Codex CLI or pass -MockResultPath for tests.")
            Write-Host "REVIEW_FAILED: Codex CLI missing."
            exit $Script:ExitReviewFailed
        }

        # Allowlisted review workspace outside the repo (git blobs only; secret isolation).
        $workspaceDir = Join-Path ([System.IO.Path]::GetTempPath()) (
            "codex-review-" + $shortSha + "-" + [guid]::NewGuid().ToString("N").Substring(0, 8)
        )
        $rootFull = [System.IO.Path]::GetFullPath($root).TrimEnd('\', '/')
        $wsFull = [System.IO.Path]::GetFullPath($workspaceDir).TrimEnd('\', '/')
        $underRepo = $false
        if ($wsFull.Length -ge $rootFull.Length) {
            $prefix = $wsFull.Substring(0, $rootFull.Length)
            if ($prefix.Equals($rootFull, [System.StringComparison]::OrdinalIgnoreCase)) {
                $next = if ($wsFull.Length -gt $rootFull.Length) { $wsFull[$rootFull.Length] } else { [char]0 }
                if ($wsFull.Length -eq $rootFull.Length -or $next -eq '\' -or $next -eq '/') {
                    $underRepo = $true
                }
            }
        }
        if ($underRepo) {
            Write-ReviewFailedResult -ResultPath $resultPath `
                -Summary "Review workspace must not be under the repository root." `
                -ReviewedBase $reviewedBase -ReviewedHead $reviewedHead -ReviewedDiffHash $diffHash `
                -ReviewNotes @("workspace=$workspaceDir", "repo=$root")
            Write-Host "REVIEW_FAILED: workspace under repo root"
            exit $Script:ExitReviewFailed
        }

        $buildWs = Join-Path $Script:AgentLoopDir "build_review_workspace.py"
        $agentsSrc = Join-Path $root "AGENTS.md"
        $buildArgs = @(
            $buildWs,
            "--repo-root", $root,
            "--diff", $diffPath,
            "--out-dir", $workspaceDir,
            "--prompt", $promptPath,
            "--schema", $schemaPath,
            "--git-rev", $reviewedHead
        )
        if (Test-Path -LiteralPath $agentsSrc) {
            $buildArgs += @("--agents", $agentsSrc)
        }
        & python @buildArgs
        $buildCode = $LASTEXITCODE
        if ($buildCode -eq 1) {
            Write-ReviewFailedResult -ResultPath $resultPath `
                -Summary "Deny-listed path(s) in diff; refusing to build Codex workspace (fail-closed)." `
                -ReviewedBase $reviewedBase -ReviewedHead $reviewedHead -ReviewedDiffHash $diffHash `
                -ReviewNotes @("build_review_workspace.py exited 1")
            Write-Host "REVIEW_FAILED: deny-listed path in diff (build exit 1)"
            exit $Script:ExitReviewFailed
        }
        if ($buildCode -ne 0) {
            Write-ReviewFailedResult -ResultPath $resultPath `
                -Summary "Failed to build allowlisted review workspace (exit $buildCode)." `
                -ReviewedBase $reviewedBase -ReviewedHead $reviewedHead -ReviewedDiffHash $diffHash
            Write-Host "REVIEW_FAILED: build_review_workspace exit $buildCode"
            exit $Script:ExitReviewFailed
        }

        $wsPrompt = Join-Path $workspaceDir "codex-review-prompt.md"
        $wsSchema = Join-Path $workspaceDir "codex-review-schema.json"
        $wsDiff = Join-Path $workspaceDir "current-diff.patch"
        $wsInput = Join-Path $workspaceDir "current-review-input.txt"
        Copy-Item -LiteralPath $inputSummaryPath -Destination $wsInput -Force

        $instructionPath = Join-Path $workspaceDir "codex-instruction.txt"
        # stdout must live outside the repo: OS isolation may chmod 000 the tree.
        $codexOutPath = Join-Path ([System.IO.Path]::GetTempPath()) (
            "codex-stdout-" + $shortSha + "-" + [guid]::NewGuid().ToString("N").Substring(0, 8) + ".json"
        )
        $codexHomeDir = Join-Path $workspaceDir "codex-home"
        New-Item -ItemType Directory -Force -Path $codexHomeDir | Out-Null

        $instruction = @"
Read-only review. Do not write files into the repository tree.

HARD SCOPE: You may ONLY read files inside this review workspace directory:
$workspaceDir

The repository tree is intentionally unreadable during this review. Only files
materialized in this workspace (git blobs + review artifacts) are in scope.

Do NOT read parent repo files, .env, .codex, credentials, or any path outside this workspace.
Refuse to use content obtained from outside the workspace.

Follow the prompt file exactly:
$wsPrompt

Review this git diff patch (source of truth):
$wsDiff

Output MUST be a single JSON object matching schema:
$wsSchema

Use these ref values exactly:
reviewed_base=$reviewedBase
reviewed_head=$reviewedHead
reviewed_diff_hash=$diffHash

Review input summary:
$wsInput
"@
        $utf8 = New-Object System.Text.UTF8Encoding $false
        [System.IO.File]::WriteAllText($instructionPath, $instruction, $utf8)

        try {
            $codexArgList = New-CodexExecArgumentList -Bin $resolvedCodexBin -InstructionPath $instructionPath
        }
        catch {
            Write-ReviewFailedResult -ResultPath $resultPath `
                -Summary "Cannot apply required Codex read-only sandbox flags: $($_.Exception.Message)" `
                -ReviewedBase $reviewedBase -ReviewedHead $reviewedHead -ReviewedDiffHash $diffHash `
                -ReviewNotes @($_.Exception.Message)
            Write-Host "REVIEW_FAILED: Codex sandbox flags unavailable."
            exit $Script:ExitReviewFailed
        }

        # Prefer read-only exec; never use write-to-repo modes.
        # Run with cwd=workspace and CODEX_HOME isolated so user config/secrets are not loaded.
        $prevEap = $ErrorActionPreference
        $prevCodexHome = $env:CODEX_HOME
        $repoModeSaved = $null
        $repoLocked = $false
        $isolationFailSummary = $null
        $skipOsIsolation = ($env:AGENT_LOOP_SKIP_OS_ISOLATION -eq "1")
        $isUnix = $false
        if ($skipOsIsolation) {
            # Tests / mocks may skip chmod isolation.
        }
        elseif ($PSVersionTable.PSVersion.Major -ge 6 -and ($IsLinux -or $IsMacOS)) {
            $isUnix = $true
        }
        else {
            $prevUnameEap = $ErrorActionPreference
            $ErrorActionPreference = "Continue"
            $unameOut = & uname 2>$null
            $ErrorActionPreference = $prevUnameEap
            if ($LASTEXITCODE -eq 0 -and -not [string]::IsNullOrWhiteSpace([string]$unameOut)) {
                $isUnix = $true
            }
        }

        if (-not $skipOsIsolation -and -not $isUnix) {
            Write-ReviewFailedResult -ResultPath $resultPath `
                -Summary "OS isolation not available on this platform." `
                -ReviewedBase $reviewedBase -ReviewedHead $reviewedHead -ReviewedDiffHash $diffHash `
                -ReviewNotes @("Set AGENT_LOOP_SKIP_OS_ISOLATION=1 only for tests/mocks.")
            Write-Host "REVIEW_FAILED: OS isolation not available on this platform"
            exit $Script:ExitReviewFailed
        }

        # Seed auth.json only into isolated CODEX_HOME (no other user Codex config).
        $authDest = Join-Path $codexHomeDir "auth.json"
        $authCopied = $false
        $authCandidates = [System.Collections.Generic.List[string]]::new()
        # Test/override source first (file-based login path without reading full user config).
        if (-not [string]::IsNullOrWhiteSpace($env:AGENT_LOOP_AUTH_JSON_SOURCE)) {
            $authCandidates.Add($env:AGENT_LOOP_AUTH_JSON_SOURCE.Trim()) | Out-Null
        }
        if (-not [string]::IsNullOrWhiteSpace($prevCodexHome)) {
            $authCandidates.Add((Join-Path $prevCodexHome "auth.json")) | Out-Null
        }
        if (-not [string]::IsNullOrWhiteSpace($env:HOME)) {
            $authCandidates.Add((Join-Path $env:HOME ".codex/auth.json")) | Out-Null
        }
        if (-not [string]::IsNullOrWhiteSpace($env:USERPROFILE)) {
            $authCandidates.Add((Join-Path $env:USERPROFILE ".codex\auth.json")) | Out-Null
        }
        foreach ($cand in $authCandidates) {
            if (Test-Path -LiteralPath $cand) {
                Copy-Item -LiteralPath $cand -Destination $authDest -Force
                $authCopied = $true
                break
            }
        }
        $isPyMockBin = ($resolvedCodexBin -match '\.py$')
        $requireAuth = (-not $isPyMockBin) -or ($env:AGENT_LOOP_REQUIRE_AUTH -eq "1")
        if ($requireAuth -and -not $authCopied) {
            Write-ReviewFailedResult -ResultPath $resultPath `
                -Summary "Codex auth.json not found; cannot run live review with isolated CODEX_HOME." `
                -ReviewedBase $reviewedBase -ReviewedHead $reviewedHead -ReviewedDiffHash $diffHash `
                -ReviewNotes @("Expected auth under prior CODEX_HOME or ~/.codex/auth.json")
            Write-Host "REVIEW_FAILED: missing Codex auth.json"
            exit $Script:ExitReviewFailed
        }

        $ErrorActionPreference = "Continue"
        $env:CODEX_HOME = $codexHomeDir
        $codexExit = -1
        try {
            if (-not $skipOsIsolation -and $isUnix) {
                $repoModeSaved = (& stat -c '%a' $root 2>$null)
                if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace([string]$repoModeSaved)) {
                    $isolationFailSummary = "Failed to read repository mode for OS isolation."
                }
                else {
                    $repoModeSaved = ([string]$repoModeSaved).Trim()
                    & chmod 000 $root
                    if ($LASTEXITCODE -ne 0) {
                        $isolationFailSummary = "Failed to lock repository (chmod 000) for OS isolation."
                    }
                    else {
                        $repoLocked = $true
                        $stillReadable = $false
                        try {
                            Get-ChildItem -LiteralPath $root -ErrorAction Stop | Out-Null
                            $stillReadable = $true
                        }
                        catch {
                            $stillReadable = $false
                        }
                        if ($stillReadable) {
                            $isolationFailSummary = "OS isolation failed: repository remained readable after chmod 000."
                        }
                    }
                }
            }

            if ([string]::IsNullOrWhiteSpace($isolationFailSummary)) {
                Push-Location -LiteralPath $workspaceDir
                try {
                    Invoke-CodexCommand -Bin $resolvedCodexBin -ArgumentList $codexArgList 2>&1 |
                        Tee-Object -FilePath $codexOutPath | Out-Null
                    $codexExit = $LASTEXITCODE
                }
                finally {
                    Pop-Location
                }
            }
        }
        finally {
            if ($repoLocked -and -not [string]::IsNullOrWhiteSpace([string]$repoModeSaved)) {
                $prevRestoreEap = $ErrorActionPreference
                $ErrorActionPreference = "Continue"
                & chmod $repoModeSaved $root 2>$null | Out-Null
                $ErrorActionPreference = $prevRestoreEap
                $repoLocked = $false
            }
            if ($null -eq $prevCodexHome -or $prevCodexHome -eq "") {
                Remove-Item Env:CODEX_HOME -ErrorAction SilentlyContinue
            }
            else {
                $env:CODEX_HOME = $prevCodexHome
            }
            $ErrorActionPreference = $prevEap
            # Best-effort cleanup of temp workspace (OK to leave under temp).
            # Tests may set AGENT_LOOP_KEEP_WORKSPACE=1 to inspect CODEX_HOME / manifest.
            $keepWorkspace = ($env:AGENT_LOOP_KEEP_WORKSPACE -eq "1")
            if (
                -not $keepWorkspace -and
                -not [string]::IsNullOrWhiteSpace($workspaceDir) -and
                (Test-Path -LiteralPath $workspaceDir)
            ) {
                try {
                    Remove-Item -LiteralPath $workspaceDir -Recurse -Force -ErrorAction SilentlyContinue
                }
                catch {
                    # leave under temp
                }
            }
        }

        if (-not [string]::IsNullOrWhiteSpace($isolationFailSummary)) {
            Write-ReviewFailedResult -ResultPath $resultPath `
                -Summary $isolationFailSummary `
                -ReviewedBase $reviewedBase -ReviewedHead $reviewedHead -ReviewedDiffHash $diffHash
            Write-Host "REVIEW_FAILED: $isolationFailSummary"
            exit $Script:ExitReviewFailed
        }

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

    # After Codex/mock returns: refuse APPROVED if HEAD or diff drifted.
    Assert-PostCodexHeadFresh `
        -ReviewedHead $reviewedHead `
        -ReviewedBase $reviewedBase `
        -DiffHash $diffHash `
        -DiffPath $diffPath `
        -HeadRefParam $HeadRef `
        -DiffFileParam $DiffFile

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

    # History copy (UTC ms stamp; never overwrite existing)
    $histPath = Get-UniqueHistoryPath -HistoryDir $historyDir -ShortSha $shortSha
    $histName = Split-Path -Leaf $histPath
    Copy-Item -LiteralPath $resultPath -Destination $histPath

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
