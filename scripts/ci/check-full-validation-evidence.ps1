param(
    [Parameter(Mandatory = $true)]
    [string]$ManifestPath,
    [Parameter(Mandatory = $true)]
    [string]$ExpectedCommitSha,
    [Parameter(Mandatory = $true)]
    [string]$ExpectedRunId
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

if ($ExpectedCommitSha -cnotmatch '^[0-9a-f]{40}$') {
    throw "ExpectedCommitSha must be a full lowercase 40-character SHA."
}
if ($ExpectedRunId -notmatch '^[1-9][0-9]*$') {
    throw "ExpectedRunId must be a positive integer."
}
if (-not (Test-Path -LiteralPath $ManifestPath -PathType Leaf)) {
    throw "Full validation evidence manifest is missing."
}

$expected = [System.Collections.Generic.Dictionary[string, string]]::new([System.StringComparer]::Ordinal)
$expected.Add("schema", "pinjie-mall-full-validation-v1")
$expected.Add("commit_sha", $ExpectedCommitSha)
$expected.Add("workflow_run_id", $ExpectedRunId)
$expected.Add("backend", "pytest")
$expected.Add("admin", "vitest,production-build,nginx-dist")
$expected.Add("browser", "playwright-chromium")
$expected.Add("database", "postgresql-18.4-alpine")
$expected.Add("cache", "redis-8.10.0-alpine")

$actual = [System.Collections.Generic.Dictionary[string, string]]::new([System.StringComparer]::Ordinal)
foreach ($line in [System.IO.File]::ReadAllLines($ManifestPath, [System.Text.Encoding]::UTF8)) {
    if ([string]::IsNullOrWhiteSpace($line)) {
        throw "Full validation evidence contains an empty line."
    }
    $separatorIndex = $line.IndexOf('=')
    if ($separatorIndex -le 0) {
        throw "Full validation evidence contains a malformed field."
    }
    $key = $line.Substring(0, $separatorIndex)
    $value = $line.Substring($separatorIndex + 1)
    if ($actual.ContainsKey($key)) {
        throw "Full validation evidence contains duplicate field '$key'."
    }
    if ($key -ne "workflow_run_attempt" -and -not $expected.ContainsKey($key)) {
        throw "Full validation evidence contains unexpected field '$key'."
    }
    $actual.Add($key, $value)
}

foreach ($entry in $expected.GetEnumerator()) {
    if (-not $actual.ContainsKey($entry.Key)) {
        throw "Full validation evidence is missing field '$($entry.Key)'."
    }
    if ($actual[$entry.Key] -cne $entry.Value) {
        throw "Full validation evidence field '$($entry.Key)' does not match."
    }
}

if (-not $actual.ContainsKey("workflow_run_attempt")) {
    throw "Full validation evidence is missing field 'workflow_run_attempt'."
}
if ($actual["workflow_run_attempt"] -notmatch '^[1-9][0-9]*$') {
    throw "Full validation evidence field 'workflow_run_attempt' must be a positive integer."
}
if ($actual.Count -ne ($expected.Count + 1)) {
    throw "Full validation evidence field count does not match the schema."
}

Write-Host "Full validation evidence matches commit $ExpectedCommitSha and workflow run $ExpectedRunId."

exit 0
