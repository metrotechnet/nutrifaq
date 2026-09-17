param(
    [string]$BaseUrl = "http://127.0.0.1:8080",
    [bool]$IncludeExtractDocx = $true,
    [bool]$IncludeExtractReferences = $true,
    [bool]$RunEachStepFirst = $true,
    [int]$TimeoutSec = 1800
)

$ErrorActionPreference = "Stop"

function Invoke-ApiRequest {
    param(
        [Parameter(Mandatory = $true)] [string]$Method,
        [Parameter(Mandatory = $true)] [string]$Url,
        [object]$Body = $null,
        [int]$Timeout = 300
    )

    try {
        if ($null -ne $Body) {
            $json = $Body | ConvertTo-Json -Depth 10
            $response = Invoke-RestMethod -Uri $Url -Method $Method -ContentType "application/json" -Body $json -TimeoutSec $Timeout
        }
        else {
            $response = Invoke-RestMethod -Uri $Url -Method $Method -TimeoutSec $Timeout
        }

        return [pscustomobject]@{
            ok = $true
            response = $response
            error = $null
        }
    }
    catch {
        $message = $_.Exception.Message
        $statusCode = $null
        $content = ""

        if ($_.Exception.Response) {
            try {
                $statusCode = [int]$_.Exception.Response.StatusCode
            }
            catch {
                $statusCode = $null
            }

            try {
                $stream = $_.Exception.Response.GetResponseStream()
                if ($stream) {
                    $reader = New-Object System.IO.StreamReader($stream)
                    $content = $reader.ReadToEnd()
                }
            }
            catch {
            }
        }

        return [pscustomobject]@{
            ok = $false
            response = $null
            error = [pscustomobject]@{
                message = $message
                statusCode = $statusCode
                body = $content
            }
        }
    }
}

function Write-Section {
    param([string]$Text)
    Write-Host ""
    Write-Host "=== $Text ==="
}

function Assert-Ok {
    param(
        [Parameter(Mandatory = $true)] $Result,
        [Parameter(Mandatory = $true)] [string]$Context
    )

    if (-not $Result.ok) {
        Write-Host "FAILED: $Context"
        if ($Result.error.statusCode) {
            Write-Host "Status: $($Result.error.statusCode)"
        }
        Write-Host "Message: $($Result.error.message)"
        if ($Result.error.body) {
            Write-Host "Body:"
            Write-Host $Result.error.body
        }
        exit 1
    }
}

$normalizedBase = $BaseUrl.TrimEnd("/")
$stepsUrl = "$normalizedBase/api/database/steps"
$regenUrl = "$normalizedBase/api/database/regenerate"

Write-Section "Database regeneration API test"
Write-Host "Base URL: $normalizedBase"
Write-Host "IncludeExtractDocx: $IncludeExtractDocx"
Write-Host "IncludeExtractReferences: $IncludeExtractReferences"
Write-Host "RunEachStepFirst: $RunEachStepFirst"

Write-Section "Check service health"
$healthResult = Invoke-ApiRequest -Method "GET" -Url "$normalizedBase/health" -Timeout 60
Assert-Ok -Result $healthResult -Context "GET /health"
Write-Host "Health response:"
$healthResult.response | ConvertTo-Json -Depth 10

Write-Section "List regeneration steps"
$stepsResult = Invoke-ApiRequest -Method "GET" -Url $stepsUrl -Timeout 60
Assert-Ok -Result $stepsResult -Context "GET /api/database/steps"
$stepsPayload = $stepsResult.response
$stepsPayload | ConvertTo-Json -Depth 10

if ($RunEachStepFirst) {
    $stepEndpoints = @(
        "/api/database/generate-transcripts-json",
        "/api/database/index-chromadb-json"
    )

    if ($IncludeExtractDocx) {
        $stepEndpoints = @("/api/database/extract-docx") + $stepEndpoints
    }
    if ($IncludeExtractReferences) {
        $stepEndpoints = @("/api/database/extract-references") + $stepEndpoints
    }

    Write-Section "Run each step endpoint"
    foreach ($endpoint in $stepEndpoints) {
        $url = "$normalizedBase$endpoint"
        Write-Host "POST $endpoint"
        $stepResult = Invoke-ApiRequest -Method "POST" -Url $url -Timeout $TimeoutSec
        Assert-Ok -Result $stepResult -Context "POST $endpoint"

        $payload = $stepResult.response
        if ($payload.status -and $payload.status -notin @("ok", "success")) {
            Write-Host "FAILED: Step returned status '$($payload.status)'"
            $payload | ConvertTo-Json -Depth 10
            exit 1
        }
        $payload | ConvertTo-Json -Depth 10
    }
}

Write-Section "Run full regeneration pipeline"
$params = @()
if ($IncludeExtractDocx) {
    $params += "include_extract_docx=true"
}
if ($IncludeExtractReferences) {
    $params += "include_extract_references=true"
}

$regenRequestUrl = $regenUrl
if ($params.Count -gt 0) {
    $regenRequestUrl = "$regenUrl?" + ($params -join "&")
}

$regenResult = Invoke-ApiRequest -Method "POST" -Url $regenRequestUrl -Timeout $TimeoutSec
Assert-Ok -Result $regenResult -Context "POST /api/database/regenerate"

$regenPayload = $regenResult.response
$regenPayload | ConvertTo-Json -Depth 15

if ($regenPayload.status -ne "success") {
    Write-Host "FAILED: Regeneration pipeline returned status '$($regenPayload.status)'"
    exit 1
}

Write-Section "Completed"
Write-Host "Database regeneration test passed."
exit 0
