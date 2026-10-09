param(
    [string]$WorkspaceScript = (Join-Path $PSScriptRoot "check-workspace-state.ps1"),
    [string]$BoundaryScript = (Join-Path $PSScriptRoot "check-module-boundaries.ps1")
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$fixtureRoot = Join-Path ([System.IO.Path]::GetTempPath()) ("pinjie-guard-tests-" + [guid]::NewGuid().ToString("N"))
$utf8 = [System.Text.UTF8Encoding]::new($false)
$powerShellExecutable = (Get-Process -Id $PID).Path

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
        [string]$Script,
        [string]$Root
    )
    $previousErrorActionPreference = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        $output = & $powerShellExecutable -NoLogo -NoProfile -ExecutionPolicy Bypass -File $Script -Root $Root *>&1
        $exitCode = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $previousErrorActionPreference
    }
    return [pscustomobject]@{
        ExitCode = $exitCode
        Output = ($output | Out-String)
    }
}

try {
    [void](New-Item -ItemType Directory -Path $fixtureRoot -Force)
    Write-Utf8File -Path (Join-Path $fixtureRoot "pnpm-lock.yaml") -Content "lockfileVersion: '9.0'`n"
    Write-Utf8File -Path (Join-Path $fixtureRoot "openapi.json") -Content "{`"openapi`":`"3.1.0`",`"info`":{`"title`":`"fixture`",`"version`":`"0.0.0`"},`"paths`":{}}`n"
    Write-Utf8File -Path (Join-Path $fixtureRoot "packages/api-client/src/index.ts") -Content "export {};`n"
    Write-Utf8File -Path (Join-Path $fixtureRoot "apps/web/package.json") -Content "{`"scripts`":{}}`n"
    Write-Utf8File -Path (Join-Path $fixtureRoot "apps/admin/package.json") -Content "{`"scripts`":{}}`n"

    $emptyResult = Invoke-Guard -Script $WorkspaceScript -Root $fixtureRoot
    if ($emptyResult.ExitCode -ne 0) {
        throw "Expected empty fixture to pass. Output: $($emptyResult.Output)"
    }

    Write-Utf8File -Path (Join-Path $fixtureRoot "apps/admin/src/features/users/internal.ts") -Content "export const internal = true;`n"
    $hiddenSourceResult = Invoke-Guard -Script $WorkspaceScript -Root $fixtureRoot
    if ($hiddenSourceResult.ExitCode -eq 0) {
        throw "Expected source without an application entry to fail."
    }
    Remove-Item -LiteralPath (Join-Path $fixtureRoot "apps/admin/src/features/users/internal.ts") -Force

    Write-Utf8File -Path (Join-Path $fixtureRoot "packages/api-client/src/generated.ts") -Content "export type Generated = unknown;`n"
    $extraClientFileResult = Invoke-Guard -Script $WorkspaceScript -Root $fixtureRoot
    if ($extraClientFileResult.ExitCode -eq 0) {
        throw "Expected an extra API Client file with placeholder OpenAPI to fail."
    }
    Remove-Item -LiteralPath (Join-Path $fixtureRoot "packages/api-client/src/generated.ts") -Force

    Write-Utf8File -Path (Join-Path $fixtureRoot "apps/web/src/app/page.tsx") -Content "export default function Page() { return null; }`n"
    $partialResult = Invoke-Guard -Script $WorkspaceScript -Root $fixtureRoot
    if ($partialResult.ExitCode -eq 0) {
        throw "Expected partial fixture to fail."
    }

    Write-Utf8File -Path (Join-Path $fixtureRoot "apps/web/package.json") -Content "{`"scripts`":{`"test`":`"vitest run`"}}`n"
    $scriptOnlyResult = Invoke-Guard -Script $WorkspaceScript -Root $fixtureRoot
    if ($scriptOnlyResult.ExitCode -eq 0) {
        throw "Expected a test script without a real test file to fail."
    }

    Write-Utf8File -Path (Join-Path $fixtureRoot "apps/web/src/app/page.test.tsx") -Content "export const pageTestFixture = true;`n"
    $readyResult = Invoke-Guard -Script $WorkspaceScript -Root $fixtureRoot
    if ($readyResult.ExitCode -ne 0) {
        throw "Expected ready fixture to pass. Output: $($readyResult.Output)"
    }

    Write-Utf8File -Path (Join-Path $fixtureRoot "apps/miniapp/src/app.tsx") -Content "export default function App() { return null; }`n"
    $miniappPartial = Invoke-Guard -Script $WorkspaceScript -Root $fixtureRoot
    if ($miniappPartial.ExitCode -eq 0) { throw "Expected partial miniapp to fail." }
    foreach ($path in @("src/app.config.ts", "config/index.ts", "src/pages/home/index.tsx")) {
        Write-Utf8File -Path (Join-Path $fixtureRoot "apps/miniapp/$path") -Content "export default {};`n"
    }
    Write-Utf8File -Path (Join-Path $fixtureRoot "apps/miniapp/project.config.json") -Content "{}`n"
    Write-Utf8File -Path (Join-Path $fixtureRoot "apps/miniapp/package.json") -Content "{`"scripts`":{`"dev:weapp`":`"taro build --type weapp --watch`",`"lint`":`"eslint src`",`"typecheck`":`"tsc --noEmit`"}}`n"
    $miniappReady = Invoke-Guard -Script $WorkspaceScript -Root $fixtureRoot
    if ($miniappReady.ExitCode -ne 0) { throw "Expected ready miniapp to pass. Output: $($miniappReady.Output)" }

    Write-Utf8File -Path (Join-Path $fixtureRoot "apps/backend/app/main.py") -Content "app = object()`n"
    Write-Utf8File -Path (Join-Path $fixtureRoot "apps/backend/tests/test_health.py") -Content "def test_health():`n    assert True`n"
    Write-Utf8File -Path (Join-Path $fixtureRoot "apps/backend/uv.lock") -Content "version = 1`n"
    Write-Utf8File -Path (Join-Path $fixtureRoot "apps/backend/alembic/env.py") -Content "# fixture`n"
    Write-Utf8File -Path (Join-Path $fixtureRoot "apps/backend/scripts/export_openapi.py") -Content "# fixture`n"
    $placeholderContractResult = Invoke-Guard -Script $WorkspaceScript -Root $fixtureRoot
    if ($placeholderContractResult.ExitCode -eq 0) {
        throw "Expected a ready Backend with placeholder contracts to fail."
    }

    Write-Utf8File -Path (Join-Path $fixtureRoot "openapi.json") -Content "{`"openapi`":`"3.1.0`",`"info`":{`"title`":`"fixture`",`"version`":`"0.0.0`"},`"paths`":{`"/health`":{`"get`":{`"responses`":{`"200`":{`"description`":`"ok`"}}}}}}`n"
    Write-Utf8File -Path (Join-Path $fixtureRoot "packages/api-client/src/index.ts") -Content "export type HealthResponse = { status: string };`n"
    $generatedContractResult = Invoke-Guard -Script $WorkspaceScript -Root $fixtureRoot
    if ($generatedContractResult.ExitCode -ne 0) {
        throw "Expected a ready Backend with generated contracts to pass. Output: $($generatedContractResult.Output)"
    }

    Write-Utf8File -Path (Join-Path $fixtureRoot "apps/backend/app/domains/auth/service.py") -Content "from app.domains.users.repository import UserRepository`n"
    $boundaryResult = Invoke-Guard -Script $BoundaryScript -Root $fixtureRoot
    if ($boundaryResult.ExitCode -eq 0) {
        throw "Expected cross-domain internal import to fail."
    }

    Write-Utf8File -Path (Join-Path $fixtureRoot "apps/web/src/features/auth/internal.ts") -Content "export const internal = true;`n"
    Write-Utf8File -Path (Join-Path $fixtureRoot "apps/web/src/features/users/example.ts") -Content "import { internal } from '../auth/internal';`n"
    $featureBoundaryResult = Invoke-Guard -Script $BoundaryScript -Root $fixtureRoot
    if ($featureBoundaryResult.ExitCode -eq 0) {
        throw "Expected cross-feature internal import to fail."
    }

    Write-Host "Governance guard fixtures passed: empty, hidden source, partial, script-only, ready, contract consistency, domain boundary, and feature boundary."
} finally {
    if (Test-Path -LiteralPath $fixtureRoot -PathType Container) {
        Remove-Item -LiteralPath $fixtureRoot -Recurse -Force
    }
}

exit 0
