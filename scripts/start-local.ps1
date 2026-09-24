[CmdletBinding()]
param(
    [switch]$ApplyPermissions
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest
$global:LASTEXITCODE = 0

$repositoryRoot = Split-Path -Parent $PSScriptRoot
$dockerDesktop = Join-Path $env:ProgramFiles "Docker\Docker\Docker Desktop.exe"

function Invoke-NativeCommand {
    param(
        [Parameter(Mandatory = $true)]
        [string]$FilePath,
        [Parameter(Mandatory = $false)]
        [string[]]$Arguments = @()
    )

    & $FilePath @Arguments
    if ($global:LASTEXITCODE -ne 0) {
        throw "命令执行失败，退出码 $global:LASTEXITCODE：$FilePath $($Arguments -join ' ')"
    }
}

function Test-DockerEngine {
    # Windows PowerShell 在 Docker 未启动时输出 stderr，通过 cmd.exe 隔离并捕获退出码。
    $global:LASTEXITCODE = 1
    cmd.exe /d /c "docker info >nul 2>nul"
    return ($global:LASTEXITCODE -eq 0)
}

Set-Location $repositoryRoot

if (-not (Test-DockerEngine)) {
    if (-not (Test-Path -LiteralPath $dockerDesktop)) {
        throw "未找到 Docker Desktop：$dockerDesktop"
    }

    Start-Process -FilePath $dockerDesktop
}

$dockerReady = $false
for ($attempt = 0; $attempt -lt 60; $attempt++) {
    if (Test-DockerEngine) {
        $dockerReady = $true
        break
    }

    Start-Sleep -Seconds 2
}

if (-not $dockerReady) {
    throw "Docker Engine 启动超时，请检查 Docker Desktop 界面"
}

Invoke-NativeCommand -FilePath "docker" -Arguments @("compose", "up", "-d", "redis")
Invoke-NativeCommand -FilePath "docker" -Arguments @("compose", "ps", "redis")
Invoke-NativeCommand -FilePath "docker" -Arguments @("compose", "exec", "-T", "redis", "redis-cli", "ping")

$backendDirectory = Join-Path $repositoryRoot "apps\backend"
Push-Location $backendDirectory
try {
    Invoke-NativeCommand -FilePath "uv" -Arguments @("run", "alembic", "upgrade", "head")
    Invoke-NativeCommand -FilePath "uv" -Arguments @(
        "run", "python", "-m", "scripts.sync_permissions", "--check",
        "--confirm-database", "pinjie_mall_dev"
    )

    if ($ApplyPermissions) {
        Invoke-NativeCommand -FilePath "uv" -Arguments @(
            "run", "python", "-m", "scripts.sync_permissions", "--apply",
            "--confirm-database", "pinjie_mall_dev"
        )
    }

    Invoke-NativeCommand -FilePath "uv" -Arguments @(
        "run", "uvicorn", "app.main:app", "--reload",
        "--host", "127.0.0.1", "--port", "18168"
    )
}
finally {
    Pop-Location
}
