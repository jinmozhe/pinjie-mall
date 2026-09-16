param(
    [string]$GuardScript = (Join-Path $PSScriptRoot "check-full-validation-evidence.ps1")
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$fixtureRoot = Join-Path ([System.IO.Path]::GetTempPath()) ("pinjie-full-validation-evidence-" + [guid]::NewGuid().ToString("N"))
$manifestPath = Join-Path $fixtureRoot "full-validation.env"
$utf8 = [System.Text.UTF8Encoding]::new($false)
$powerShellExecutable = (Get-Process -Id $PID).Path
$expectedSha = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
$expectedRunId = "987654321"
$validEvidence = @"
schema=pinjie-mall-full-validation-v1
commit_sha=$expectedSha
workflow_run_id=$expectedRunId
workflow_run_attempt=1
backend=pytest
admin=vitest,production-build,nginx-dist
browser=playwright-chromium
database=postgresql-18.4-alpine
cache=redis-8.10.0-alpine
"@

function Write-Evidence {
    param([string]$Content)
    [System.IO.File]::WriteAllText($manifestPath, $Content, $utf8)
}

function Invoke-Guard {
    $previousErrorActionPreference = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        $output = & $powerShellExecutable -NoLogo -NoProfile -ExecutionPolicy Bypass -File $GuardScript `
            -ManifestPath $manifestPath `
            -ExpectedCommitSha $expectedSha `
            -ExpectedRunId $expectedRunId *>&1
        $exitCode = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $previousErrorActionPreference
    }
    return [pscustomobject]@{ ExitCode = $exitCode; Output = ($output | Out-String) }
}

function Assert-GuardRejects {
    param(
        [string]$Scenario,
        [string]$Content
    )
    Write-Evidence -Content $Content
    if ((Invoke-Guard).ExitCode -eq 0) {
        throw "Expected full validation evidence guard to reject $Scenario."
    }
}

try {
    [void](New-Item -ItemType Directory -Path $fixtureRoot -Force)

    Write-Evidence -Content $validEvidence
    $validResult = Invoke-Guard
    if ($validResult.ExitCode -ne 0) {
        throw "Expected valid full validation evidence to pass. Output: $($validResult.Output)"
    }

    Assert-GuardRejects -Scenario "wrong commit SHA" -Content $validEvidence.Replace($expectedSha, "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb")
    Assert-GuardRejects -Scenario "legacy development-server evidence" -Content $validEvidence.Replace("pinjie-mall-full-validation-v1", "pinjie-full-validation-v1")
    Assert-GuardRejects -Scenario "smoke evidence renamed to the full filename" -Content $validEvidence.Replace("pinjie-mall-full-validation-v1", "pinjie-mall-smoke-validation-v1")
    Assert-GuardRejects -Scenario "smoke browser scope with a forged full schema" -Content $validEvidence.Replace("browser=playwright-chromium", "browser=playwright-chromium-smoke")
    Assert-GuardRejects -Scenario "missing frontend tests with a forged full schema" -Content $validEvidence.Replace("admin=vitest,production-build,nginx-dist", "admin=production-build,nginx-dist")
    Assert-GuardRejects -Scenario "wrong workflow run" -Content $validEvidence.Replace($expectedRunId, "123456789")
    Assert-GuardRejects -Scenario "missing validation field" -Content $validEvidence.Replace("backend=pytest`n", "")
    Assert-GuardRejects -Scenario "duplicate validation field" -Content ($validEvidence + "backend=pytest`n")
    Assert-GuardRejects -Scenario "unexpected validation field" -Content ($validEvidence + "result=success`n")
    Assert-GuardRejects -Scenario "invalid workflow attempt" -Content $validEvidence.Replace("workflow_run_attempt=1", "workflow_run_attempt=0")

    Write-Host "Full validation evidence guard fixtures passed: valid, SHA, run, missing, duplicate, unexpected, and attempt cases."
} finally {
    if (Test-Path -LiteralPath $fixtureRoot -PathType Container) {
        Remove-Item -LiteralPath $fixtureRoot -Recurse -Force
    }
}

exit 0
