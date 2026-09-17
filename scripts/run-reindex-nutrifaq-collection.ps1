param(
    [string]$ProjectName = "nutria",
    [string]$CollectionName = "nutrifaq-collection",
    [string]$EmbeddingModel = "text-embedding-3-small"
)

$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = Resolve-Path (Join-Path $scriptDir "..")
Set-Location $repoRoot

# Unbuffered output so progress/timing lines appear live.
$env:PYTHONUNBUFFERED = "1"

# Conservative defaults for Azure S0 throttling. Respect existing values if already set.
if (-not $env:EMBEDDING_REQUEST_BATCH_SIZE) { $env:EMBEDDING_REQUEST_BATCH_SIZE = "1" }
if (-not $env:EMBEDDING_REQUEST_PAUSE_SECONDS) { $env:EMBEDDING_REQUEST_PAUSE_SECONDS = "2" }
if (-not $env:EMBEDDING_MAX_RETRIES) { $env:EMBEDDING_MAX_RETRIES = "20" }
if (-not $env:EMBEDDING_RETRY_BASE_DELAY) { $env:EMBEDDING_RETRY_BASE_DELAY = "5" }
if (-not $env:EMBEDDING_RETRY_MAX_DELAY) { $env:EMBEDDING_RETRY_MAX_DELAY = "120" }
if (-not $env:EMBEDDING_SPLIT_AFTER_RETRIES) { $env:EMBEDDING_SPLIT_AFTER_RETRIES = "1" }
if (-not $env:LLM_RETRY_VERBOSE) { $env:LLM_RETRY_VERBOSE = "true" }
if (-not $env:RESET_COLLECTION_ON_INDEX) { $env:RESET_COLLECTION_ON_INDEX = "false" }

$python = "C:/Users/denis/AppData/Local/Programs/Python/Python311/python.exe"
if (-not (Test-Path $python)) {
    $python = "python"
}

$start = Get-Date
Write-Host "=== Reindex Start ==="
Write-Host "Start: $start"
Write-Host "Repo:  $repoRoot"
Write-Host "Project: $ProjectName"
Write-Host "Collection: $CollectionName"
Write-Host "Embedding model: $EmbeddingModel"
Write-Host "Python: $python"
Write-Host ""

$command = "from api.index_chromadb import index_project; r=index_project('$ProjectName', collection_name='$CollectionName', embedding_model='$EmbeddingModel'); print(r)"
& $python -u -c $command
$exitCode = $LASTEXITCODE

$end = Get-Date
$duration = $end - $start

Write-Host ""
Write-Host "=== Reindex End ==="
Write-Host "End: $end"
Write-Host ("Duration: {0:hh\:mm\:ss}" -f $duration)
Write-Host "ExitCode: $exitCode"

exit $exitCode
