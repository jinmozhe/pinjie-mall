param(
    [string]$Root = (Resolve-Path (Join-Path (Join-Path $PSScriptRoot "..") "..")),
    [string]$GitHubOutputPath = ""
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$rootPath = (Resolve-Path -LiteralPath $Root).Path
$failures = [System.Collections.Generic.List[string]]::new()

function Get-State {
    param(
        [Parameter(Mandatory = $true)]
        [System.Collections.IDictionary]$Markers
    )

    $presentCount = @($Markers.Values | Where-Object { $_ }).Count
    if ($presentCount -eq 0) {
        return "empty"
    }
    if ($presentCount -eq $Markers.Count) {
        return "ready"
    }
    return "partial"
}

function Get-PackageHasScript {
    param(
        [Parameter(Mandatory = $true)]
        [string]$PackagePath,
        [Parameter(Mandatory = $true)]
        [string]$ScriptName
    )

    if (-not (Test-Path -LiteralPath $PackagePath -PathType Leaf)) {
        return $false
    }

    $package = Get-Content -Raw -Encoding UTF8 -LiteralPath $PackagePath | ConvertFrom-Json
    if ($null -eq $package.scripts) {
        return $false
    }

    $script = $package.scripts.PSObject.Properties[$ScriptName]
    return $null -ne $script -and -not [string]::IsNullOrWhiteSpace([string]$script.Value)
}

function Add-StateOutput {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Name,
        [Parameter(Mandatory = $true)]
        [string]$State
    )

    if (-not [string]::IsNullOrWhiteSpace($GitHubOutputPath)) {
        Add-Content -Encoding UTF8 -LiteralPath $GitHubOutputPath -Value "$Name=$State"
    }
}

function Test-HasSourceFile {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path,
        [Parameter(Mandatory = $true)]
        [string[]]$Extensions
    )

    if (-not (Test-Path -LiteralPath $Path -PathType Container)) {
        return $false
    }

    return $null -ne (Get-ChildItem -LiteralPath $Path -Recurse -File | Where-Object {
        $Extensions -contains $_.Extension.ToLowerInvariant()
    } | Select-Object -First 1)
}

function Test-HasFrontendTestFile {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path
    )

    if (-not (Test-Path -LiteralPath $Path -PathType Container)) {
        return $false
    }

    return $null -ne (Get-ChildItem -LiteralPath $Path -Recurse -File | Where-Object {
        $_.Name -match '\.(test|spec)\.(js|jsx|ts|tsx)$'
    } | Select-Object -First 1)
}

$backendTestRoot = Join-Path $rootPath "apps/backend/tests"
$backendHasTests = $false
if (Test-Path -LiteralPath $backendTestRoot -PathType Container) {
    $backendHasTests = $null -ne (Get-ChildItem -LiteralPath $backendTestRoot -Recurse -File -Filter "test_*.py" | Select-Object -First 1)
}

$backendMarkers = [ordered]@{
    source = Test-HasSourceFile -Path (Join-Path $rootPath "apps/backend/app") -Extensions @(".py")
    main = Test-Path -LiteralPath (Join-Path $rootPath "apps/backend/app/main.py") -PathType Leaf
    tests = $backendHasTests
    lock = Test-Path -LiteralPath (Join-Path $rootPath "apps/backend/uv.lock") -PathType Leaf
    migration_env = Test-Path -LiteralPath (Join-Path $rootPath "apps/backend/alembic/env.py") -PathType Leaf
    openapi_export = Test-Path -LiteralPath (Join-Path $rootPath "apps/backend/scripts/export_openapi.py") -PathType Leaf
}
$webMarkers = [ordered]@{
    source = Test-HasSourceFile -Path (Join-Path $rootPath "apps/web/src") -Extensions @(".js", ".jsx", ".ts", ".tsx")
    entry = Test-Path -LiteralPath (Join-Path $rootPath "apps/web/src/app/page.tsx") -PathType Leaf
    test_script = Get-PackageHasScript -PackagePath (Join-Path $rootPath "apps/web/package.json") -ScriptName "test"
    tests = Test-HasFrontendTestFile -Path (Join-Path $rootPath "apps/web/src")
}
$adminMarkers = [ordered]@{
    source = Test-HasSourceFile -Path (Join-Path $rootPath "apps/admin/src") -Extensions @(".js", ".jsx", ".ts", ".tsx")
    entry = (Test-Path -LiteralPath (Join-Path $rootPath "apps/admin/src/main.tsx") -PathType Leaf) -or
        (Test-Path -LiteralPath (Join-Path $rootPath "apps/admin/src/app.tsx") -PathType Leaf)
    test_script = Get-PackageHasScript -PackagePath (Join-Path $rootPath "apps/admin/package.json") -ScriptName "test"
    tests = Test-HasFrontendTestFile -Path (Join-Path $rootPath "apps/admin/src")
}

$states = [ordered]@{
    backend = Get-State -Markers $backendMarkers
    web = Get-State -Markers $webMarkers
    admin = Get-State -Markers $adminMarkers
}

$miniappRoot = Join-Path $rootPath "apps/miniapp"
$miniappHasSource = Test-HasSourceFile -Path (Join-Path $miniappRoot "src") -Extensions @(".ts", ".tsx", ".js", ".jsx")
$miniappMarkers = [ordered]@{
    source = $miniappHasSource
    entry = Test-Path -LiteralPath (Join-Path $miniappRoot "src/app.tsx") -PathType Leaf
    app_config = Test-Path -LiteralPath (Join-Path $miniappRoot "src/app.config.ts") -PathType Leaf
    compiler = Test-Path -LiteralPath (Join-Path $miniappRoot "config/index.ts") -PathType Leaf
    project = Test-Path -LiteralPath (Join-Path $miniappRoot "project.config.json") -PathType Leaf
    home = Test-Path -LiteralPath (Join-Path $miniappRoot "src/pages/home/index.tsx") -PathType Leaf
    dev_script = Get-PackageHasScript -PackagePath (Join-Path $miniappRoot "package.json") -ScriptName "dev:weapp"
    lint_script = Get-PackageHasScript -PackagePath (Join-Path $miniappRoot "package.json") -ScriptName "lint"
    typecheck_script = Get-PackageHasScript -PackagePath (Join-Path $miniappRoot "package.json") -ScriptName "typecheck"
}
$states.Add("miniapp", (Get-State -Markers $miniappMarkers))

if (-not (Test-Path -LiteralPath (Join-Path $rootPath "pnpm-lock.yaml") -PathType Leaf)) {
    $failures.Add("Root pnpm-lock.yaml is missing.")
}

foreach ($entry in $states.GetEnumerator()) {
    Add-StateOutput -Name $entry.Key -State $entry.Value
    if ($entry.Value -eq "partial") {
        $markers = switch ($entry.Key) {
            "backend" { $backendMarkers }
            "web" { $webMarkers }
            "admin" { $adminMarkers }
            "miniapp" { $miniappMarkers }
        }
        $detail = ($markers.GetEnumerator() | ForEach-Object { "$($_.Key)=$($_.Value)" }) -join ", "
        $failures.Add("$($entry.Key) is partial: $detail")
    }
}

$openApiPath = Join-Path $rootPath "openapi.json"
$apiClientPath = Join-Path $rootPath "packages/api-client/src/index.ts"
if (-not (Test-Path -LiteralPath $openApiPath -PathType Leaf)) {
    $failures.Add("Root openapi.json is missing.")
} elseif (-not (Test-Path -LiteralPath $apiClientPath -PathType Leaf)) {
    $failures.Add("API Client entry is missing.")
} else {
    $openApi = Get-Content -Raw -Encoding UTF8 -LiteralPath $openApiPath | ConvertFrom-Json
    $pathCount = @($openApi.paths.PSObject.Properties).Count
    $apiClientContent = Get-Content -Raw -Encoding UTF8 -LiteralPath $apiClientPath
    $apiClientFiles = @(Get-ChildItem -LiteralPath (Split-Path -Parent $apiClientPath) -Recurse -File)
    $apiClientPayload = [regex]::Replace($apiClientContent, '(?m)^\s*//.*(?:\r?\n|$)', '').Trim()
    $clientIsPlaceholder = $apiClientFiles.Count -eq 1 -and $apiClientPayload -match '^export\s*\{\s*\};$'
    $contractState = if ($pathCount -eq 0 -and $clientIsPlaceholder) {
        "placeholder"
    } elseif ($pathCount -gt 0 -and -not $clientIsPlaceholder) {
        "generated"
    } else {
        "partial"
    }
    Add-StateOutput -Name "contract" -State $contractState

    if ($contractState -eq "partial") {
        $failures.Add("OpenAPI and API Client are inconsistent: both must be placeholders or both must be generated.")
    }
    if ($states.backend -eq "empty" -and $contractState -ne "placeholder") {
        $failures.Add("OpenAPI and API Client must both remain placeholders while Backend is empty.")
    }
    if ($states.backend -eq "ready" -and $contractState -ne "generated") {
        $failures.Add("OpenAPI and API Client must both be generated when Backend is ready.")
    }
}

foreach ($entry in $states.GetEnumerator()) {
    Write-Host "$($entry.Key): $($entry.Value)"
}

if ($failures.Count -gt 0) {
    foreach ($failure in $failures) {
        Write-Error $failure
    }
    exit 1
}

Write-Host "Workspace state is valid. Empty means governance-only, not application quality passed."
