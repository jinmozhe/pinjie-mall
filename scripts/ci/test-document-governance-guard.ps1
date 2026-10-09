param(
    [string]$GuardScript = (Join-Path $PSScriptRoot "check-document-governance.ps1")
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$fixtureRoot = Join-Path ([System.IO.Path]::GetTempPath()) ("pinjie-document-governance-tests-" + [guid]::NewGuid().ToString("N"))
$utf8 = [System.Text.UTF8Encoding]::new($false)
$powerShellExecutable = (Get-Process -Id $PID).Path
$planPath = "plans/2026-08-29_fixture-plan.md"
$planIndexPath = Join-Path $fixtureRoot "plans/INDEX.md"
$projectIndexPath = Join-Path $fixtureRoot "PROJECT_INDEX.md"
$statusInProgress = -join @([char]0x5B9E, [char]0x65BD, [char]0x4E2D)
$resultNotApplicable = -join @([char]0x4E0D, [char]0x9002, [char]0x7528)
$resultCompleted = -join @([char]0x5DF2, [char]0x5B8C, [char]0x6210)

function Write-Utf8File {
    param(
        [string]$Path,
        [string]$Content
    )
    $parent = Split-Path -Parent $Path
    if (-not (Test-Path -LiteralPath $parent -PathType Container)) {
        [void](New-Item -ItemType Directory -Path $parent -Force)
    }
    [System.IO.File]::WriteAllText($Path, $Content, $utf8)
}

function Invoke-Guard {
    param(
        [int]$InstructionLimitBytes = 32768,
        [int]$InstructionMinimumRemainingBytes = 1024
    )
    $previousErrorActionPreference = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        $output = & $powerShellExecutable -NoLogo -NoProfile -ExecutionPolicy Bypass -File $GuardScript `
            -Root $fixtureRoot `
            -InstructionLimitBytes $InstructionLimitBytes `
            -InstructionMinimumRemainingBytes $InstructionMinimumRemainingBytes *>&1
        $exitCode = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $previousErrorActionPreference
    }
    return [pscustomobject]@{
        ExitCode = $exitCode
        Output = ($output | Out-String)
    }
}

function Assert-GuardPasses {
    $result = Invoke-Guard
    if ($result.ExitCode -ne 0) {
        throw "Expected document governance fixture to pass. Output: $($result.Output)"
    }
}

function Assert-GuardFails {
    param(
        [string]$Scenario,
        [string]$ExpectedOutput,
        [int]$InstructionLimitBytes = 32768,
        [int]$InstructionMinimumRemainingBytes = 1024
    )
    $result = Invoke-Guard -InstructionLimitBytes $InstructionLimitBytes -InstructionMinimumRemainingBytes $InstructionMinimumRemainingBytes
    if ($result.ExitCode -eq 0) {
        throw "Expected document governance fixture to reject $Scenario."
    }
    $normalizedOutput = $result.Output -replace '\s', ''
    $normalizedExpectedOutput = $ExpectedOutput -replace '\s', ''
    if (-not $normalizedOutput.Contains($normalizedExpectedOutput)) {
        throw "Expected $Scenario output to contain '$ExpectedOutput'. Actual output: $($result.Output)"
    }
}

try {
    [void](New-Item -ItemType Directory -Path $fixtureRoot -Force)
    & git -C $fixtureRoot init --quiet
    if ($LASTEXITCODE -ne 0) {
        throw "Unable to initialize document governance fixture repository."
    }

    $planIndex = @"
# Plan index

| Path | Status | Result | Scope | Purpose |
| --- | --- | --- | --- | --- |
| ``$planPath`` | $statusInProgress | $resultNotApplicable | Documentation | Validate document governance |
"@
    $projectIndex = @"
# Project index

## Active plans

| Plan | Status | Work |
| --- | --- | --- |
| [Fixture plan]($planPath) | $statusInProgress | Validate document governance |
"@

    Write-Utf8File -Path (Join-Path $fixtureRoot "AGENTS.md") -Content "# Root rules`n"
    Write-Utf8File -Path (Join-Path $fixtureRoot "apps/backend/AGENTS.md") -Content "# Backend rules`n"
    Write-Utf8File -Path (Join-Path $fixtureRoot "apps/admin/AGENTS.md") -Content "# Admin rules`n"
    Write-Utf8File -Path (Join-Path $fixtureRoot "apps/miniapp/AGENTS.md") -Content "# Miniapp rules`n"
    Write-Utf8File -Path (Join-Path $fixtureRoot "apps/web/AGENTS.md") -Content "# Web rules`n"
    Write-Utf8File -Path (Join-Path $fixtureRoot ".agents/rules/00-repository.md") -Content "@../../AGENTS.md`n"
    Write-Utf8File -Path (Join-Path $fixtureRoot ".agents/rules/10-backend.md") -Content "@../../apps/backend/AGENTS.md`n"
    Write-Utf8File -Path (Join-Path $fixtureRoot ".agents/rules/20-admin.md") -Content "@../../apps/admin/AGENTS.md`n"
    Write-Utf8File -Path (Join-Path $fixtureRoot ".agents/rules/30-web.md") -Content "@../../apps/web/AGENTS.md`n"
    Write-Utf8File -Path (Join-Path $fixtureRoot ".agents/rules/40-miniapp.md") -Content "@../../apps/miniapp/AGENTS.md`n"
    Write-Utf8File -Path (Join-Path $fixtureRoot "plans/README.md") -Content "# Plan rules`n"
    Write-Utf8File -Path $planIndexPath -Content ($planIndex + "`n")
    Write-Utf8File -Path (Join-Path $fixtureRoot $planPath) -Content "# Fixture plan`n"
    Write-Utf8File -Path $projectIndexPath -Content ($projectIndex + "`n")
    Write-Utf8File -Path (Join-Path $fixtureRoot "docs/README.md") -Content "# Topic docs index`n`n| File | Description |`n| --- | --- |`n| [example.md](example.md) | Example |`n"
    Write-Utf8File -Path (Join-Path $fixtureRoot "docs/example.md") -Content "# Example topic document`n"

    Assert-GuardPasses

    $retiredIndexName = "agents" + "-index.md"
    $retiredIndexPath = Join-Path $fixtureRoot (".agents/" + $retiredIndexName)
    Write-Utf8File -Path $retiredIndexPath -Content "# retired`n"
    Assert-GuardFails -Scenario "a retired index path" -ExpectedOutput "retired project index"
    Remove-Item -LiteralPath $retiredIndexPath -Force

    $unregisteredPlanPath = Join-Path $fixtureRoot "plans/2026-08-29_unregistered-plan.md"
    Write-Utf8File -Path $unregisteredPlanPath -Content "# Unregistered plan`n"
    Assert-GuardFails -Scenario "an unregistered plan" -ExpectedOutput "missing from plans/INDEX.md"
    Remove-Item -LiteralPath $unregisteredPlanPath -Force

    Write-Utf8File -Path $planIndexPath -Content ($planIndex + "`n| ``$planPath`` | $statusInProgress | $resultNotApplicable | Documentation | Duplicate |`n")
    Assert-GuardFails -Scenario "a duplicate plan registration" -ExpectedOutput "more than once"
    Write-Utf8File -Path $planIndexPath -Content ($planIndex + "`n")

    $activePlanCells = '\| ' + [regex]::Escape($statusInProgress) + ' \| ' + [regex]::Escape($resultNotApplicable) + ' \|'
    $invalidStatusCells = '| invalid | ' + $resultNotApplicable + ' |'
    $invalidResultCells = '| ' + $statusInProgress + ' | ' + $resultCompleted + ' |'
    Write-Utf8File -Path $planIndexPath -Content (($planIndex -replace $activePlanCells, $invalidStatusCells) + "`n")
    Assert-GuardFails -Scenario "an invalid plan status" -ExpectedOutput "invalid status"
    Write-Utf8File -Path $planIndexPath -Content (($planIndex -replace $activePlanCells, $invalidResultCells) + "`n")
    Assert-GuardFails -Scenario "an invalid active plan result" -ExpectedOutput "non-empty result"
    Write-Utf8File -Path $planIndexPath -Content ($planIndex + "`n")

    Write-Utf8File -Path $projectIndexPath -Content "# Project index`n`n## Active plans`n`nNo active plans.`n"
    Assert-GuardFails -Scenario "active plan drift" -ExpectedOutput "missing active plan"
    Write-Utf8File -Path $projectIndexPath -Content ($projectIndex + "`n")

    $unregisteredDocPath = Join-Path $fixtureRoot "docs/unregistered.md"
    Write-Utf8File -Path $unregisteredDocPath -Content "# Unregistered topic document`n"
    Assert-GuardFails -Scenario "an unregistered topic document" -ExpectedOutput "missing from docs/README.md"
    Remove-Item -LiteralPath $unregisteredDocPath -Force

    $webBridgePath = Join-Path $fixtureRoot ".agents/rules/30-web.md"
    Remove-Item -LiteralPath $webBridgePath -Force
    Assert-GuardFails -Scenario "a missing Antigravity bridge" -ExpectedOutput ".agents/rules/30-web.md is required"
    Write-Utf8File -Path $webBridgePath -Content "@../../apps/web/AGENTS.md`n"

    Assert-GuardFails -Scenario "an oversized instruction chain" -ExpectedOutput "reserved capacity" -InstructionLimitBytes 16 -InstructionMinimumRemainingBytes 0
    Assert-GuardPasses

    Write-Host "Document governance guard fixtures passed: valid, retired path, plan registration, status, result, activity, docs, bridge, and instruction capacity."
} finally {
    if (Test-Path -LiteralPath $fixtureRoot -PathType Container) {
        Remove-Item -LiteralPath $fixtureRoot -Recurse -Force
    }
}

exit 0
