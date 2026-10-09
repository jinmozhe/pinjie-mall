param(
    [string]$Root = (Resolve-Path (Join-Path (Join-Path $PSScriptRoot "..") "..")),
    [int]$InstructionLimitBytes = 32768,
    [int]$InstructionMinimumRemainingBytes = 1024
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$rootPath = (Resolve-Path -LiteralPath $Root).Path
$issues = [System.Collections.Generic.List[string]]::new()
$pathComparer = [System.StringComparer]::OrdinalIgnoreCase
$utf8 = [System.Text.UTF8Encoding]::new($false, $true)
$statusPendingConfirmation = -join @([char]0x5F85, [char]0x786E, [char]0x8BA4)
$statusPendingImplementation = -join @([char]0x5F85, [char]0x5B9E, [char]0x65BD)
$statusInProgress = -join @([char]0x5B9E, [char]0x65BD, [char]0x4E2D)
$statusEnded = -join @([char]0x5DF2, [char]0x7ED3, [char]0x675F)
$resultNotApplicable = -join @([char]0x4E0D, [char]0x9002, [char]0x7528)
$resultCompleted = -join @([char]0x5DF2, [char]0x5B8C, [char]0x6210)
$resultCancelled = -join @([char]0x5DF2, [char]0x53D6, [char]0x6D88)
$resultReplaced = -join @([char]0x5DF2, [char]0x66FF, [char]0x4EE3)
$fullWidthSemicolon = [char]0xFF1B

function Add-Issue {
    param([string]$Message)
    $issues.Add($Message)
}

function Get-NormalizedRelativePath {
    param([string]$Path)
    return $Path.Replace("\", "/")
}

function Get-Text {
    param([string]$Path)
    return [System.IO.File]::ReadAllText($Path, $utf8)
}

function Get-RelativePath {
    param(
        [string]$BasePath,
        [string]$TargetPath
    )
    $baseFullPath = [System.IO.Path]::GetFullPath($BasePath).TrimEnd("\", "/") + [System.IO.Path]::DirectorySeparatorChar
    $targetFullPath = [System.IO.Path]::GetFullPath($TargetPath)
    $baseUri = [System.Uri]::new($baseFullPath)
    $targetUri = [System.Uri]::new($targetFullPath)
    return [System.Uri]::UnescapeDataString($baseUri.MakeRelativeUri($targetUri).ToString())
}

if ($InstructionLimitBytes -le 0) {
    throw "InstructionLimitBytes must be greater than zero."
}
if ($InstructionMinimumRemainingBytes -lt 0 -or $InstructionMinimumRemainingBytes -ge $InstructionLimitBytes) {
    throw "InstructionMinimumRemainingBytes must be non-negative and lower than InstructionLimitBytes."
}

$repositoryFiles = @(& git -C $rootPath -c core.quotepath=false ls-files --cached --others --exclude-standard)
if ($LASTEXITCODE -ne 0) {
    throw "Unable to enumerate repository files."
}
$repositoryFiles = @($repositoryFiles | ForEach-Object { Get-NormalizedRelativePath $_ })

$requiredFiles = @(
    "AGENTS.md",
    "PROJECT_INDEX.md",
    "plans/README.md",
    "plans/INDEX.md",
    "docs/README.md"
)
foreach ($relativePath in $requiredFiles) {
    if (-not (Test-Path -LiteralPath (Join-Path $rootPath $relativePath) -PathType Leaf)) {
        Add-Issue "$relativePath is required."
    }
}

$textExtensions = @(
    ".css", ".example", ".html", ".ini", ".js", ".json", ".jsx", ".md",
    ".mjs", ".ps1", ".py", ".svg", ".toml", ".ts", ".tsx", ".txt", ".yaml", ".yml"
)
$retiredIndexName = "agents" + "-index.md"
$retiredIndexDirectoryPath = ".agents/" + $retiredIndexName
$retiredProjectIndexPath = ".agents/" + "PROJECT_INDEX.md"
foreach ($relativePath in $repositoryFiles) {
    if ($relativePath.Equals($retiredIndexName, [System.StringComparison]::OrdinalIgnoreCase) -or
        $relativePath.Equals($retiredIndexDirectoryPath, [System.StringComparison]::OrdinalIgnoreCase) -or
        $relativePath.Equals($retiredProjectIndexPath, [System.StringComparison]::OrdinalIgnoreCase)) {
        Add-Issue "$relativePath is a retired project index path."
    }
    $fullPath = Join-Path $rootPath $relativePath
    if (-not (Test-Path -LiteralPath $fullPath -PathType Leaf)) {
        continue
    }
    $extension = [System.IO.Path]::GetExtension($relativePath).ToLowerInvariant()
    if ($textExtensions -notcontains $extension) {
        continue
    }
    $text = Get-Text $fullPath
    $normalizedText = $text.Replace("\", "/")
    if ($normalizedText.IndexOf($retiredIndexName, [System.StringComparison]::OrdinalIgnoreCase) -ge 0 -or
        $normalizedText.IndexOf($retiredIndexDirectoryPath, [System.StringComparison]::OrdinalIgnoreCase) -ge 0 -or
        $normalizedText.IndexOf($retiredProjectIndexPath, [System.StringComparison]::OrdinalIgnoreCase) -ge 0) {
        Add-Issue "$relativePath references a retired project index name or path."
    }
}

$expectedRuleFiles = @(
    "AGENTS.md",
    "apps/backend/AGENTS.md",
    "apps/admin/AGENTS.md",
    "apps/miniapp/AGENTS.md",
    "apps/web/AGENTS.md"
)
$actualRuleFiles = @($repositoryFiles | Where-Object { $_ -match "(^|/)AGENTS\.md$" })
foreach ($relativePath in $expectedRuleFiles) {
    if ($actualRuleFiles -notcontains $relativePath) {
        Add-Issue "$relativePath is required as a project rule source."
    }
}
foreach ($relativePath in $actualRuleFiles) {
    if ($expectedRuleFiles -notcontains $relativePath) {
        Add-Issue "$relativePath is an unexpected additional project rule source."
    }
}
foreach ($relativePath in $repositoryFiles) {
    if ([System.IO.Path]::GetFileName($relativePath).Equals("AGENTS.override.md", [System.StringComparison]::OrdinalIgnoreCase)) {
        Add-Issue "$relativePath is not allowed; permanent project rules belong in AGENTS.md."
    }
}
if ($repositoryFiles -contains ".agents/AGENTS.md") {
    Add-Issue ".agents/AGENTS.md is not allowed; .agents only contains Antigravity rule bridges."
}

$bridgeExpectations = [ordered]@{
    ".agents/rules/00-repository.md" = "@../../AGENTS.md"
    ".agents/rules/10-backend.md" = "@../../apps/backend/AGENTS.md"
    ".agents/rules/20-admin.md" = "@../../apps/admin/AGENTS.md"
    ".agents/rules/30-web.md" = "@../../apps/web/AGENTS.md"
    ".agents/rules/40-miniapp.md" = "@../../apps/miniapp/AGENTS.md"
}
foreach ($entry in $bridgeExpectations.GetEnumerator()) {
    $bridgePath = Join-Path $rootPath $entry.Key
    if (-not (Test-Path -LiteralPath $bridgePath -PathType Leaf)) {
        Add-Issue "$($entry.Key) is required."
        continue
    }
    $bridgeText = Get-Text $bridgePath
    if (-not $bridgeText.Contains([string]$entry.Value)) {
        Add-Issue "$($entry.Key) must reference $($entry.Value)."
    }
}

$rootRulePath = Join-Path $rootPath "AGENTS.md"
if (Test-Path -LiteralPath $rootRulePath -PathType Leaf) {
    $rootRuleBytes = $utf8.GetByteCount((Get-Text $rootRulePath))
    $maximumCombinedBytes = $InstructionLimitBytes - $InstructionMinimumRemainingBytes
    foreach ($relativePath in $expectedRuleFiles | Where-Object { $_ -ne "AGENTS.md" }) {
        $applicationRulePath = Join-Path $rootPath $relativePath
        if (-not (Test-Path -LiteralPath $applicationRulePath -PathType Leaf)) {
            continue
        }
        $applicationRuleBytes = $utf8.GetByteCount((Get-Text $applicationRulePath))
        $combinedBytes = $rootRuleBytes + $applicationRuleBytes
        if ($combinedBytes -gt $maximumCombinedBytes) {
            Add-Issue "$relativePath combines with root AGENTS.md to $combinedBytes bytes; maximum with reserved capacity is $maximumCombinedBytes bytes."
        }
    }
}

$planDirectory = Join-Path $rootPath "plans"
$planIndexPath = Join-Path $planDirectory "INDEX.md"
$projectIndexPath = Join-Path $rootPath "PROJECT_INDEX.md"
if ((Test-Path -LiteralPath $planDirectory -PathType Container) -and
    (Test-Path -LiteralPath $planIndexPath -PathType Leaf) -and
    (Test-Path -LiteralPath $projectIndexPath -PathType Leaf)) {
    $planFiles = [System.Collections.Generic.HashSet[string]]::new($pathComparer)
    Get-ChildItem -LiteralPath $planDirectory -File -Filter "*.md" |
        Where-Object { $_.Name -notin @("README.md", "INDEX.md") } |
        ForEach-Object { [void]$planFiles.Add("plans/" + $_.Name) }

    $planIndexText = Get-Text $planIndexPath
    $entryPattern = '(?m)^\| `(?<path>plans/[^`\r\n]+\.md)` \| (?<status>[^|\r\n]+?) \| (?<result>[^|\r\n]+?) \|'
    $entryMatches = [regex]::Matches($planIndexText, $entryPattern)
    $indexedPlans = [System.Collections.Generic.HashSet[string]]::new($pathComparer)
    $activePlans = [System.Collections.Generic.Dictionary[string, string]]::new($pathComparer)
    $allowedStatuses = @($statusPendingConfirmation, $statusPendingImplementation, $statusInProgress, $statusEnded)
    $endedResultPattern = "^(" +
        [regex]::Escape($resultCompleted) + "|" +
        [regex]::Escape($resultCancelled) + "|" +
        [regex]::Escape($resultReplaced) + ")(" +
        [regex]::Escape([string]$fullWidthSemicolon) + ".*)?$"
    foreach ($match in $entryMatches) {
        $path = Get-NormalizedRelativePath $match.Groups["path"].Value.Trim()
        $status = $match.Groups["status"].Value.Trim()
        $result = $match.Groups["result"].Value.Trim()
        if (-not $indexedPlans.Add($path)) {
            Add-Issue "plans/INDEX.md registers $path more than once."
        }
        if ($allowedStatuses -notcontains $status) {
            Add-Issue "plans/INDEX.md uses invalid status '$status' for $path."
        } elseif ($status -eq $statusEnded) {
            if ($result -notmatch $endedResultPattern) {
                Add-Issue "plans/INDEX.md uses invalid ended result '$result' for $path."
            }
        } else {
            if ($result -ne $resultNotApplicable) {
                Add-Issue "plans/INDEX.md uses a non-empty result for active plan $path."
            }
            if (-not $activePlans.ContainsKey($path)) {
                $activePlans.Add($path, $status)
            }
        }
    }

    foreach ($path in $planFiles) {
        if (-not $indexedPlans.Contains($path)) {
            Add-Issue "$path is missing from plans/INDEX.md."
        }
    }
    foreach ($path in $indexedPlans) {
        if (-not $planFiles.Contains($path)) {
            Add-Issue "plans/INDEX.md registers missing plan file $path."
        }
    }

    $projectIndexText = Get-Text $projectIndexPath
    $activityPattern = '(?m)^\| \[[^\]]+\]\((?<path>plans/[^)\r\n]+\.md)\) \| (?<status>[^|\r\n]+?) \|'
    $activityMatches = [regex]::Matches($projectIndexText, $activityPattern)
    $projectActivities = [System.Collections.Generic.Dictionary[string, string]]::new($pathComparer)
    foreach ($match in $activityMatches) {
        $path = Get-NormalizedRelativePath ([System.Uri]::UnescapeDataString($match.Groups["path"].Value.Trim()))
        $status = $match.Groups["status"].Value.Trim()
        if ($projectActivities.ContainsKey($path)) {
            Add-Issue "PROJECT_INDEX.md lists active plan $path more than once."
        } else {
            $projectActivities.Add($path, $status)
        }
    }
    foreach ($entry in $activePlans.GetEnumerator()) {
        if (-not $projectActivities.ContainsKey($entry.Key)) {
            Add-Issue "PROJECT_INDEX.md is missing active plan $($entry.Key)."
        } elseif ($projectActivities[$entry.Key] -ne $entry.Value) {
            Add-Issue "PROJECT_INDEX.md status for $($entry.Key) does not match plans/INDEX.md."
        }
    }
    foreach ($entry in $projectActivities.GetEnumerator()) {
        if (-not $activePlans.ContainsKey($entry.Key)) {
            Add-Issue "PROJECT_INDEX.md lists non-active or unregistered plan $($entry.Key)."
        }
    }
}

$docsDirectory = Join-Path $rootPath "docs"
$docsIndexPath = Join-Path $docsDirectory "README.md"
if ((Test-Path -LiteralPath $docsDirectory -PathType Container) -and
    (Test-Path -LiteralPath $docsIndexPath -PathType Leaf)) {
    $docsFiles = [System.Collections.Generic.HashSet[string]]::new($pathComparer)
    Get-ChildItem -LiteralPath $docsDirectory -Recurse -File -Filter "*.md" |
        Where-Object { $_.FullName -ne $docsIndexPath } |
        ForEach-Object {
            [void]$docsFiles.Add((Get-NormalizedRelativePath (Get-RelativePath -BasePath $docsDirectory -TargetPath $_.FullName)))
        }

    $docsIndexText = Get-Text $docsIndexPath
    $linkMatches = [regex]::Matches($docsIndexText, '\]\((?<target>[^)#?]+\.md)(?:#[^)]*)?\)')
    $indexedDocs = [System.Collections.Generic.HashSet[string]]::new($pathComparer)
    foreach ($match in $linkMatches) {
        $target = [System.Uri]::UnescapeDataString($match.Groups["target"].Value)
        $resolvedTarget = [System.IO.Path]::GetFullPath((Join-Path $docsDirectory $target))
        $relativeTarget = Get-NormalizedRelativePath (Get-RelativePath -BasePath $docsDirectory -TargetPath $resolvedTarget)
        if ($relativeTarget.StartsWith("../", [System.StringComparison]::Ordinal)) {
            continue
        }
        if (-not $indexedDocs.Add($relativeTarget)) {
            Add-Issue "docs/README.md registers $relativeTarget more than once."
        }
        if (-not (Test-Path -LiteralPath $resolvedTarget -PathType Leaf)) {
            Add-Issue "docs/README.md references missing document $relativeTarget."
        }
    }
    foreach ($path in $docsFiles) {
        if (-not $indexedDocs.Contains($path)) {
            Add-Issue "docs/$path is missing from docs/README.md."
        }
    }
    foreach ($path in $indexedDocs) {
        if (-not $docsFiles.Contains($path)) {
            Add-Issue "docs/README.md registers non-document path $path."
        }
    }
}

if ($issues.Count -gt 0) {
    foreach ($issue in $issues) {
        Write-Host "ERROR: $issue"
    }
    exit 1
}

Write-Host "Document governance checks passed: retired paths, rules, bridges, instruction capacity, plan indexes, activities, and docs index."
