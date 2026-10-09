param(
    [string]$Root = (Resolve-Path (Join-Path (Join-Path $PSScriptRoot "..") ".."))
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$rootPath = (Resolve-Path -LiteralPath $Root).Path
$violations = [System.Collections.Generic.List[string]]::new()
$sourceExtensions = @(".py", ".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs")
$directorySeparator = [System.IO.Path]::DirectorySeparatorChar
$excludedDirectories = [System.Collections.Generic.HashSet[string]]::new(
    [System.StringComparer]::OrdinalIgnoreCase
)
foreach ($directoryName in @("node_modules", ".next", "dist", "coverage", ".venv", ".pytest_cache", ".pytest-cache-runtime", ".pytest-tmp", "__pycache__")) {
    [void]$excludedDirectories.Add($directoryName)
}

function Convert-ToForwardSlashPath {
    param([string]$Path)
    return $Path.Replace("\", "/")
}

function Add-Violation {
    param(
        [string]$File,
        [int]$Line,
        [string]$Message
    )
    $rootPrefix = $rootPath.TrimEnd("\", "/") + $directorySeparator
    $relative = if ($File.StartsWith($rootPrefix, [System.StringComparison]::OrdinalIgnoreCase)) {
        Convert-ToForwardSlashPath -Path $File.Substring($rootPrefix.Length)
    } else {
        Convert-ToForwardSlashPath -Path $File
    }
    $violations.Add("${relative}:${Line}: $Message")
}

function Get-SourceFiles {
    param([string]$Path)
    if (-not (Test-Path -LiteralPath $Path -PathType Container)) {
        return @()
    }

    $files = [System.Collections.Generic.List[System.IO.FileInfo]]::new()
    $pending = [System.Collections.Generic.Stack[string]]::new()
    $pending.Push($Path)
    while ($pending.Count -gt 0) {
        $current = $pending.Pop()
        foreach ($item in Get-ChildItem -Force -LiteralPath $current) {
            if ($item.PSIsContainer) {
                if (-not $excludedDirectories.Contains($item.Name)) {
                    $pending.Push($item.FullName)
                }
                continue
            }
            if ($sourceExtensions -contains $item.Extension) {
                $files.Add($item)
            }
        }
    }
    return @($files)
}

function Get-ImportSpecifiers {
    param([string]$Line)
    $matches = [regex]::Matches($Line, '(?:from\s+|import\s*\(|require\s*\()\s*[''"]([^''"]+)[''"]')
    return @($matches | ForEach-Object { $_.Groups[1].Value })
}

$applicationRoots = [ordered]@{
    backend = Join-Path $rootPath "apps/backend"
    web = Join-Path $rootPath "apps/web"
    admin = Join-Path $rootPath "apps/admin"
    miniapp = Join-Path $rootPath "apps/miniapp"
}

foreach ($app in $applicationRoots.GetEnumerator()) {
    foreach ($file in Get-SourceFiles -Path $app.Value) {
        $lineNumber = 0
        foreach ($line in Get-Content -Encoding UTF8 -LiteralPath $file.FullName) {
            $lineNumber++
            foreach ($otherApp in $applicationRoots.GetEnumerator()) {
                if ($otherApp.Key -eq $app.Key) {
                    continue
                }
                $patterns = @(
                    "apps/$($otherApp.Key)/",
                    "@pinjie/$($otherApp.Key)"
                )
                foreach ($pattern in $patterns) {
                    if ($line -like "*$pattern*") {
                        Add-Violation -File $file.FullName -Line $lineNumber -Message "Application $($app.Key) must not import application $($otherApp.Key)."
                    }
                }
            }
        }
    }
}

$packagesRoot = Join-Path $rootPath "packages"
foreach ($file in Get-SourceFiles -Path $packagesRoot) {
    $lineNumber = 0
    foreach ($line in Get-Content -Encoding UTF8 -LiteralPath $file.FullName) {
        $lineNumber++
        if ($line -match '(?:^|[''"])(?:\.\.?/)*apps/|@pinjie/(?:web|admin|backend|miniapp)') {
            Add-Violation -File $file.FullName -Line $lineNumber -Message "packages must not depend on apps."
        }
    }
}

foreach ($frontendName in @("web", "admin")) {
    $featuresRoot = Join-Path $rootPath "apps/$frontendName/src/features"
    if (-not (Test-Path -LiteralPath $featuresRoot -PathType Container)) {
        continue
    }

    foreach ($sourceFeature in Get-ChildItem -LiteralPath $featuresRoot -Directory) {
        foreach ($file in Get-SourceFiles -Path $sourceFeature.FullName) {
            $lineNumber = 0
            foreach ($line in Get-Content -Encoding UTF8 -LiteralPath $file.FullName) {
                $lineNumber++
                foreach ($specifier in Get-ImportSpecifiers -Line $line) {
                    $aliasMatch = [regex]::Match($specifier, "^@/features/([^/]+)(/.*)?$")
                    if ($aliasMatch.Success) {
                        $targetFeature = $aliasMatch.Groups[1].Value
                        $internalPath = $aliasMatch.Groups[2].Value
                        if ($targetFeature -ne $sourceFeature.Name -and -not [string]::IsNullOrWhiteSpace($internalPath)) {
                            Add-Violation -File $file.FullName -Line $lineNumber -Message "Feature $($sourceFeature.Name) must not import internal paths from Feature $targetFeature."
                        }
                    }

                    if ($specifier.StartsWith(".")) {
                        $resolved = [System.IO.Path]::GetFullPath((Join-Path $file.DirectoryName $specifier))
                        $featuresPrefix = $featuresRoot.TrimEnd("\", "/") + $directorySeparator
                        if ($resolved.StartsWith($featuresPrefix, [System.StringComparison]::OrdinalIgnoreCase)) {
                            $relativeTarget = Convert-ToForwardSlashPath -Path $resolved.Substring($featuresPrefix.Length)
                            $targetFeature = $relativeTarget.Split("/")[0]
                            if ($targetFeature -ne $sourceFeature.Name) {
                                $targetLeaf = [System.IO.Path]::GetFileName($resolved)
                                if ($targetLeaf -notin @($targetFeature, "index", "index.ts", "index.tsx")) {
                                    Add-Violation -File $file.FullName -Line $lineNumber -Message "Feature $($sourceFeature.Name) must not import internal paths from Feature $targetFeature."
                                }
                            }
                        }
                    }
                }
            }
        }
    }
}

$domainsRoot = Join-Path $rootPath "apps/backend/app/domains"
if (Test-Path -LiteralPath $domainsRoot -PathType Container) {
    foreach ($sourceDomain in Get-ChildItem -LiteralPath $domainsRoot -Directory) {
        foreach ($file in Get-SourceFiles -Path $sourceDomain.FullName) {
            $lineNumber = 0
            foreach ($line in Get-Content -Encoding UTF8 -LiteralPath $file.FullName) {
                $lineNumber++
                $match = [regex]::Match($line, "(?:from|import)\s+app\.domains\.([A-Za-z0-9_]+)\.([A-Za-z0-9_]+)")
                if ($match.Success) {
                    $targetDomain = $match.Groups[1].Value
                    $targetModule = $match.Groups[2].Value
                    if ($targetDomain -ne $sourceDomain.Name -and $targetModule -match "^(repository|repositories|model|models|service|services)$") {
                        Add-Violation -File $file.FullName -Line $lineNumber -Message "Domain $($sourceDomain.Name) must not import internal module $targetDomain.$targetModule."
                    }
                }
            }
        }
    }
}

if ($violations.Count -gt 0) {
    foreach ($violation in $violations) {
        Write-Error $violation
    }
    exit 1
}

Write-Host "Static module boundary checks passed. Dynamic imports and cycles require later architecture tests."
