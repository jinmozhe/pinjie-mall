param(
    [string]$Root = (Resolve-Path (Join-Path (Join-Path $PSScriptRoot "..") ".."))
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$rootPath = (Resolve-Path -LiteralPath $Root).Path
$composePath = Join-Path $rootPath "compose.prod.yml"
if (-not (Test-Path -LiteralPath $composePath -PathType Leaf)) {
    throw "Production Compose file is missing: $composePath"
}

$compose = [System.IO.File]::ReadAllText($composePath, [System.Text.Encoding]::UTF8)
$violations = [System.Collections.Generic.List[string]]::new()

function Get-ServiceBlock {
    param([string]$Name)

    $pattern = "(?ms)^  " + [regex]::Escape($Name) + ":\r?\n(?<body>.*?)(?=^  [A-Za-z0-9_-]+:\r?$|^(?:volumes|networks):\r?$)"
    $match = [regex]::Match($compose, $pattern)
    if (-not $match.Success) {
        $violations.Add("Service '$Name' is missing from compose.prod.yml.")
        return ""
    }
    return $match.Groups["body"].Value
}

function Get-ServiceImage {
    param(
        [string]$Name,
        [string]$ServiceBlock
    )

    $match = [regex]::Match($ServiceBlock, '(?m)^    image:\s*(?<image>.+?)\s*$')
    if (-not $match.Success) {
        $violations.Add("Service '$Name' must declare exactly one image reference.")
        return ""
    }
    return $match.Groups["image"].Value
}

function Test-ImmutableImageReference {
    param([string]$Reference)

    return $Reference -match '^[A-Za-z0-9][A-Za-z0-9._/-]*(?::[A-Za-z0-9][A-Za-z0-9._-]*)?@sha256:[0-9a-f]{64}$'
}

function Confirm-RequiredImageVariable {
    param(
        [string]$Name,
        [string]$VariableName
    )

    $serviceBlock = Get-ServiceBlock -Name $Name
    $reference = Get-ServiceImage -Name $Name -ServiceBlock $serviceBlock
    $expectedReference = '${' + $VariableName + '}'
    if ($reference -ne $expectedReference) {
        $violations.Add("Service '$Name' must use the '$VariableName' immutable image variable.")
    }

    $configuredReference = [Environment]::GetEnvironmentVariable($VariableName)
    if ($null -ne $configuredReference -and -not (Test-ImmutableImageReference -Reference $configuredReference)) {
        $violations.Add("Environment variable '$VariableName' must be a complete immutable image digest when provided.")
    }
}

function Confirm-DockerfileBaseImages {
    param([string]$RelativePath)

    $dockerfilePath = Join-Path $rootPath $RelativePath
    if (-not (Test-Path -LiteralPath $dockerfilePath -PathType Leaf)) {
        $violations.Add("Production Dockerfile is missing: $RelativePath.")
        return
    }

    $dockerfile = [System.IO.File]::ReadAllText($dockerfilePath, [System.Text.Encoding]::UTF8)
    $fromMatches = [regex]::Matches($dockerfile, '(?m)^FROM\s+(?<image>\S+)(?:\s+AS\s+\S+)?\s*$')
    if ($fromMatches.Count -eq 0) {
        $violations.Add("Production Dockerfile '$RelativePath' must declare at least one base image.")
        return
    }

    foreach ($fromMatch in $fromMatches) {
        $reference = $fromMatch.Groups["image"].Value
        if (-not (Test-ImmutableImageReference -Reference $reference)) {
            $violations.Add("Production Dockerfile '$RelativePath' base image '$reference' must use a complete immutable digest.")
        }
    }
}

foreach ($dockerfilePath in @("apps/backend/Dockerfile", "apps/admin/Dockerfile")) {
    Confirm-DockerfileBaseImages -RelativePath $dockerfilePath
}

Confirm-RequiredImageVariable -Name "backend" -VariableName "BACKEND_IMAGE"
Confirm-RequiredImageVariable -Name "request-log-consumer" -VariableName "BACKEND_IMAGE"
Confirm-RequiredImageVariable -Name "admin" -VariableName "ADMIN_IMAGE"

foreach ($forbiddenService in @("postgres", "redis", "web")) {
    if ($compose -match ("(?m)^  " + [regex]::Escape($forbiddenService) + ":\s*$")) {
        $violations.Add("Shared production infrastructure must not declare a local '$forbiddenService' service.")
    }
}

foreach ($forbiddenVolume in @("postgres_data", "redis_data")) {
    if ($compose -match ("(?m)^  " + [regex]::Escape($forbiddenVolume) + ":\s*$")) {
        $violations.Add("Shared production infrastructure must not declare a local '$forbiddenVolume' volume.")
    }
}

if ($compose -notmatch '(?ms)^networks:\r?\n  infrastructure:\r?\n    name: 1panel-network\r?\n    external: true\s*$') {
    $violations.Add("Production Compose must map the external 'infrastructure' network to '1panel-network'.")
}

foreach ($serviceName in @("backend", "request-log-consumer")) {
    $serviceBlock = Get-ServiceBlock -Name $serviceName
    if ($serviceBlock -notmatch '(?m)^      LOG_FILE_ENABLED: "false"\s*$') {
        $violations.Add("Service '$serviceName' must explicitly disable file logging unless a writable log volume is configured.")
    }
    if ($serviceBlock -notmatch '(?ms)^    networks:\r?\n      - default\r?\n      - infrastructure\s*$') {
        $violations.Add("Service '$serviceName' must join both the project default network and shared infrastructure network.")
    }
    if ($serviceBlock -match '(?m)^    depends_on:\s*$') {
        $violations.Add("Service '$serviceName' must rely on readiness checks instead of Compose dependencies for shared infrastructure.")
    }
}

foreach ($frontendService in @("admin")) {
    $serviceBlock = Get-ServiceBlock -Name $frontendService
    if ($serviceBlock -match '(?m)^\s+- infrastructure\s*$') {
        $violations.Add("Service '$frontendService' must not connect directly to the shared infrastructure network.")
    }
}

if ($violations.Count -gt 0) {
    foreach ($violation in $violations) {
        Write-Error $violation
    }
    exit 1
}

Write-Host "Production deployment invariants passed: immutable app images, shared infrastructure network, service isolation, and container logging policy."
