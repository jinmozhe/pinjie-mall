param(
    [string]$GuardScript = (Join-Path $PSScriptRoot "check-production-compose.ps1")
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$fixtureRoot = Join-Path ([System.IO.Path]::GetTempPath()) ("pinjie-production-compose-guard-" + [guid]::NewGuid().ToString("N"))
$composePath = Join-Path $fixtureRoot "compose.prod.yml"
$backendDockerfilePath = Join-Path $fixtureRoot "apps/backend/Dockerfile"
$adminDockerfilePath = Join-Path $fixtureRoot "apps/admin/Dockerfile"
$webDockerfilePath = Join-Path $fixtureRoot "apps/web/Dockerfile"
$utf8 = [System.Text.UTF8Encoding]::new($false)
$powerShellExecutable = (Get-Process -Id $PID).Path

function Write-Compose {
    param([string]$Content)
    [System.IO.File]::WriteAllText($composePath, $Content, $utf8)
}

function Write-Dockerfiles {
    [System.IO.File]::WriteAllText(
        $backendDockerfilePath,
        "FROM python:3.14.7-slim-trixie@sha256:ce40764625a4ff50df3548277632e7f96c4e77fe75fa848aae9885476e7df5a4 AS runtime`n",
        $utf8
    )
    [System.IO.File]::WriteAllText(
        $adminDockerfilePath,
        "FROM nginx:1.29-alpine@sha256:5616878291a2eed594aee8db4dade5878cf7edcb475e59193904b198d9b830de AS runtime`n",
        $utf8
    )
    [System.IO.File]::WriteAllText(
        $webDockerfilePath,
        "FROM node:24-alpine@sha256:d32cdf619f63fe0471182d08996dd516c6275bb5fd31ae06e55a570bd9e1ad43 AS runtime`n",
        $utf8
    )
}

function Invoke-Guard {
    $previousErrorActionPreference = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        $output = & $powerShellExecutable -NoLogo -NoProfile -ExecutionPolicy Bypass -File $GuardScript -Root $fixtureRoot *>&1
        $exitCode = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $previousErrorActionPreference
    }
    return [pscustomobject]@{ ExitCode = $exitCode; Output = ($output | Out-String) }
}

$validCompose = @'
services:
  backend:
    image: ${BACKEND_IMAGE}
    environment:
      LOG_FILE_ENABLED: "false"
    networks:
      - default
      - infrastructure
  request-log-consumer:
    image: ${BACKEND_IMAGE}
    environment:
      LOG_FILE_ENABLED: "false"
    networks:
      - default
      - infrastructure
  admin:
    image: ${ADMIN_IMAGE}
networks:
  infrastructure:
    name: 1panel-network
    external: true
'@

try {
    [void](New-Item -ItemType Directory -Path (Split-Path $backendDockerfilePath) -Force)
    [void](New-Item -ItemType Directory -Path (Split-Path $adminDockerfilePath) -Force)
    [void](New-Item -ItemType Directory -Path (Split-Path $webDockerfilePath) -Force)
    Write-Dockerfiles
    Write-Compose -Content $validCompose
    $validResult = Invoke-Guard
    if ($validResult.ExitCode -ne 0) {
        throw "Expected the valid production Compose fixture to pass. Output: $($validResult.Output)"
    }

    Write-Compose -Content $validCompose.Replace("    external: true", "    external: false")
    if ((Invoke-Guard).ExitCode -eq 0) {
        throw "Expected a non-external infrastructure network to fail."
    }

    Write-Compose -Content $validCompose.Replace("      - infrastructure", "")
    if ((Invoke-Guard).ExitCode -eq 0) {
        throw "Expected missing infrastructure service memberships to fail."
    }

    Write-Compose -Content $validCompose.Replace(
        "  backend:",
        "  backend:`n    depends_on:`n      postgresql:`n        condition: service_healthy"
    )
    if ((Invoke-Guard).ExitCode -eq 0) {
        throw "Expected a shared infrastructure Compose dependency to fail."
    }

    Write-Compose -Content $validCompose.Replace(
        "  admin:",
        "  admin:`n    networks:`n      - default`n      - infrastructure"
    )
    if ((Invoke-Guard).ExitCode -eq 0) {
        throw "Expected a frontend infrastructure network membership to fail."
    }

    Write-Compose -Content $validCompose.Replace("services:", "services:`n  postgres:`n    image: postgres:18.4-alpine")
    if ((Invoke-Guard).ExitCode -eq 0) {
        throw "Expected a local PostgreSQL service to fail."
    }

    Write-Compose -Content $validCompose.Replace("services:", 'services:' + "`n" + '  web:' + "`n" + '    image: ${WEB_IMAGE}')
    if ((Invoke-Guard).ExitCode -eq 0) {
        throw "Expected a frozen Web service without host ports to fail."
    }

    Write-Compose -Content ($validCompose + "`nvolumes:`n  redis_data:`n")
    if ((Invoke-Guard).ExitCode -eq 0) {
        throw "Expected a local Redis volume to fail."
    }

    Write-Compose -Content $validCompose.Replace('      LOG_FILE_ENABLED: "false"', "")
    if ((Invoke-Guard).ExitCode -eq 0) {
        throw "Expected missing production file-log overrides to fail."
    }

    Write-Compose -Content $validCompose.Replace('${ADMIN_IMAGE}', '${BACKEND_IMAGE}')
    if ((Invoke-Guard).ExitCode -eq 0) {
        throw "Expected an incorrect application image variable to fail."
    }

    $previousBackendImage = [Environment]::GetEnvironmentVariable("BACKEND_IMAGE")
    try {
        [Environment]::SetEnvironmentVariable("BACKEND_IMAGE", "ghcr.io/example/backend:latest")
        Write-Compose -Content $validCompose
        if ((Invoke-Guard).ExitCode -eq 0) {
            throw "Expected a mutable configured application image to fail."
        }
    } finally {
        [Environment]::SetEnvironmentVariable("BACKEND_IMAGE", $previousBackendImage)
    }

    [System.IO.File]::WriteAllText($adminDockerfilePath, "FROM node:24-alpine AS runtime`n", $utf8)
    Write-Compose -Content $validCompose
    if ((Invoke-Guard).ExitCode -eq 0) {
        throw "Expected a mutable Dockerfile base image to fail."
    }

    Write-Host "Production deployment guard fixtures passed: valid and all Dockerfile, Compose, network, isolation, and logging negatives."
} finally {
    if (Test-Path -LiteralPath $fixtureRoot -PathType Container) {
        Remove-Item -LiteralPath $fixtureRoot -Recurse -Force
    }
}

exit 0
