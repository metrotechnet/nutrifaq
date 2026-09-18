param(
    [string]$ProjectName = "nutrifaq",
    [string]$LlmProvider = "",
    [string]$EmbeddingProvider = "",
    [switch]$IncludeExtractDocx,
    [switch]$IncludeExtractReferences,
    [string]$BackendUrl = ""
)

$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = Resolve-Path (Join-Path $scriptDir "..")
Set-Location $repoRoot

function Import-DotEnv {
    param([string]$DotEnvPath)

    if (-not (Test-Path $DotEnvPath)) {
        return
    }

    foreach ($line in Get-Content -Path $DotEnvPath) {
        $trimmed = $line.Trim()
        if ([string]::IsNullOrWhiteSpace($trimmed)) { continue }
        if ($trimmed.StartsWith("#")) { continue }
        if ($trimmed -notmatch "^[A-Za-z_][A-Za-z0-9_]*=.*$") { continue }

        $key, $value = $trimmed -split "=", 2
        if (-not [string]::IsNullOrWhiteSpace([Environment]::GetEnvironmentVariable($key, "Process"))) {
            continue
        }

        [Environment]::SetEnvironmentVariable($key, $value, "Process")
    }
}

Import-DotEnv -DotEnvPath (Join-Path $repoRoot ".env")

# Unbuffered output so progress/timing lines appear live.
$env:PYTHONUNBUFFERED = "1"

# Conservative defaults for Azure S0 throttling. Respect existing values if already set.
if (-not $env:EMBEDDING_MAX_RETRIES) { $env:EMBEDDING_MAX_RETRIES = "20" }
if (-not $env:EMBEDDING_RETRY_BASE_DELAY) { $env:EMBEDDING_RETRY_BASE_DELAY = "5" }
if (-not $env:EMBEDDING_RETRY_MAX_DELAY) { $env:EMBEDDING_RETRY_MAX_DELAY = "120" }
if (-not $env:EMBEDDING_SPLIT_AFTER_RETRIES) { $env:EMBEDDING_SPLIT_AFTER_RETRIES = "1" }

# if (-not $BackendUrl) {
#     if ($env:BACKEND_URL) {
#         $BackendUrl = $env:BACKEND_URL
#     } else {
#         $BackendUrl = "http://127.0.0.1:8080"
#     }
# }
$BackendUrl = "http://127.0.0.1:8080"
$BackendUrl = $BackendUrl.TrimEnd('/')
# print backend URL for verification
Write-Host "Backend URL: $BackendUrl"

$start = Get-Date
Write-Host "=== Reindex Start ==="
Write-Host "Start: $start"
Write-Host "Repo:  $repoRoot"
Write-Host "Project: $ProjectName"
Write-Host "Backend: $BackendUrl"
Write-Host ""

$queryParams = @(
    "include_extract_docx=$($IncludeExtractDocx.IsPresent.ToString().ToLower())",
    "include_extract_references=$($IncludeExtractReferences.IsPresent.ToString().ToLower())"
)

if ($LlmProvider) {
    $queryParams += "llm_provider=$LlmProvider"
}

if ($EmbeddingProvider) {
    $queryParams += "embedding_provider=$EmbeddingProvider"
}

$uri = "$BackendUrl/api/database/regenerate?" + ($queryParams -join "&")

$exitCode = 0
try {
    $result = Invoke-RestMethod -Uri $uri -Method POST -ContentType "application/json"
    $result | ConvertTo-Json -Depth 20
} catch {
    $exitCode = 1
    $ex = $_.Exception
    $status = ""
    $body = ""
    if ($ex.Response -ne $null) {
        try {
            $status = [int]$ex.Response.StatusCode
        } catch {
            $status = $ex.Response.StatusCode.value__
        }
        try {
            $stream = $ex.Response.GetResponseStream()
            if ($stream -ne $null) {
                $reader = New-Object System.IO.StreamReader($stream)
                $body = $reader.ReadToEnd()
            }
        } catch {
            $body = ""
        }
    }

    Write-Host "Request failed."
    if ($status) { Write-Host "Status: $status" }
    if ($body) { Write-Host $body }
    if (-not $body) { Write-Host $ex.Message }
}

$end = Get-Date
$duration = $end - $start

Write-Host ""
Write-Host "=== Reindex End ==="
Write-Host "End: $end"
Write-Host ("Duration: {0:hh\:mm\:ss}" -f $duration)
Write-Host "ExitCode: $exitCode"

exit $exitCode
