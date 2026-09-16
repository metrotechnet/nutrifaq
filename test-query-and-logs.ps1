param(
    [string]$ResourceGroup = "nutrifaq-rg",
    [string]$AppName = "nutrifaq-api",
    [string]$Question = "trace check from script",
    [string]$Language = "en",
    [string]$Timezone = "UTC",
    [string]$Locale = "en-US",
    [string]$Library = "all",
    [int]$RequestTimeoutSec = 90,
    [int]$TailLines = 120,
    [int]$PatternTailLines = 500
)

$ErrorActionPreference = "Stop"

Write-Host "== Test POST /query and collect logs =="

$azCmd = Get-Command az -ErrorAction SilentlyContinue
if (-not $azCmd) {
    throw "Azure CLI (az) is not installed or not on PATH."
}

$appHost = az webapp show --resource-group $ResourceGroup --name $AppName --query "defaultHostName" -o tsv --only-show-errors
if (-not $appHost) {
    throw "Unable to resolve defaultHostName for App Service '$AppName'."
}

$baseUrl = "https://$appHost"
$queryUrl = "$baseUrl/query"
$healthUrl = "$baseUrl/health"

Write-Host "App host: $appHost"
Write-Host "Health URL: $healthUrl"
Write-Host "Query URL: $queryUrl"

# 1) Trigger one query request
$payload = @{
    question = $Question
    agent = "agent"
    language = $Language
    timezone = $Timezone
    locale = $Locale
    session_id = $null
    bibliotheque = $Library
} | ConvertTo-Json -Depth 6

Write-Host "Sending POST /query ..."
$requestUtc = (Get-Date).ToUniversalTime()
$matchWindowStartUtc = $requestUtc.AddMinutes(-1)

try {
    $response = Invoke-WebRequest -Uri $queryUrl -Method POST -ContentType "application/json" -Body $payload -TimeoutSec $RequestTimeoutSec -UseBasicParsing
    Write-Host "POST status: $($response.StatusCode)"
    if ($response.Content) {
        $snippet = if ($response.Content.Length -gt 400) { $response.Content.Substring(0, 400) } else { $response.Content }
        Write-Host "POST response snippet:"
        Write-Host $snippet
    }
} catch {
    $status = if ($_.Exception.Response) { $_.Exception.Response.StatusCode.value__ } else { "NO_RESPONSE" }
    Write-Warning "POST /query failed. Status: $status"
    Write-Warning $_.Exception.Message
}

# 2) Download latest App Service logs
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$zipPath = Join-Path (Get-Location) ("appservice-logs-{0}.zip" -f $stamp)
$outDir = Join-Path $env:TEMP ("nutrifaq-logscan-{0}" -f $stamp)

Write-Host "Downloading logs to: $zipPath"
az webapp log download --resource-group $ResourceGroup --name $AppName --log-file $zipPath | Out-Null

if (-not (Test-Path -LiteralPath $zipPath)) {
    throw "Log archive was not created."
}

Expand-Archive -Path $zipPath -DestinationPath $outDir -Force
Write-Host "Logs extracted to: $outDir"

# 3) Show newest log files + key matches
$dockerLog = Get-ChildItem -Path (Join-Path $outDir "LogFiles") -File -Filter "*docker*.log" -ErrorAction SilentlyContinue | Sort-Object LastWriteTime -Descending | Select-Object -First 1
$startupLog = Get-ChildItem -Path (Join-Path $outDir "LogFiles\StartupLogs") -File -ErrorAction SilentlyContinue | Sort-Object LastWriteTime -Descending | Select-Object -First 1

if ($dockerLog) {
    Write-Host "Newest docker log: $($dockerLog.FullName)"
} else {
    Write-Warning "No docker log file found in archive."
}

if ($startupLog) {
    Write-Host "Newest startup log: $($startupLog.FullName)"
} else {
    Write-Warning "No startup log file found in archive."
}

$patterns = @(
    "[DEBUG][route:/query]",
    "[DEBUG][ask_question_stream]",
    "[DEBUG][query_chromadb]",
    "Traceback",
    "ModuleNotFoundError",
    "ImportError",
    "Failed to start site"
)

Write-Host ""
Write-Host "Searching for key patterns..."
$searchFiles = @()
if ($dockerLog) { $searchFiles += $dockerLog.FullName }
if ($startupLog) { $searchFiles += $startupLog.FullName }

# Fallback: if latest log pointers are missing, scan all logs.
if ($searchFiles.Count -eq 0) {
    $searchFiles = (Get-ChildItem -Path $outDir -Recurse -File | Select-Object -ExpandProperty FullName)
}

$patternMatches = @()
foreach ($file in $searchFiles) {
    $tailContent = Get-Content -Path $file -Tail $PatternTailLines -ErrorAction SilentlyContinue
    if (-not $tailContent) {
        continue
    }

    $tailMatches = $tailContent | Select-String -Pattern $patterns -SimpleMatch -ErrorAction SilentlyContinue
    foreach ($m in $tailMatches) {
        if (-not $m -or [string]::IsNullOrWhiteSpace($m.Line)) {
            continue
        }

        $lineTsUtc = $null
        if ($m.Line -match '^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z)') {
            try {
                $lineTsUtc = [DateTime]::Parse($Matches[1]).ToUniversalTime()
            } catch {
                $lineTsUtc = $null
            }
        }

        if ($lineTsUtc -and $lineTsUtc -lt $matchWindowStartUtc) {
            continue
        }

        $patternMatches += [pscustomobject]@{
            Path = $file
            TailLine = $m.LineNumber
            Line = $m.Line
        }
    }
}

if ($patternMatches.Count -eq 0) {
    Write-Host "No matching lines found for target patterns in recent log tails."
} else {
    $patternMatches | Where-Object { -not [string]::IsNullOrWhiteSpace($_.Line) } | Select-Object -First 80 | ForEach-Object {
        Write-Host ("{0}:tail#{1}: {2}" -f $_.Path, $_.TailLine, $_.Line)
    }
}

if ($dockerLog) {
    Write-Host ""
    Write-Host "--- Docker log tail ($TailLines lines) ---"
    Get-Content -Path $dockerLog.FullName -Tail $TailLines | ForEach-Object { Write-Host $_ }
}

if ($startupLog) {
    Write-Host ""
    Write-Host "--- Startup log tail ($TailLines lines) ---"
    Get-Content -Path $startupLog.FullName -Tail $TailLines | ForEach-Object { Write-Host $_ }
}

Write-Host ""
Write-Host "Done."
Write-Host "Log ZIP: $zipPath"
Write-Host "Extracted logs: $outDir"
