param(
    [string]$Url = "https://nutrifaq-api.azurewebsites.net/api/db/connection",
    [int]$TimeoutSec = 30
)

$ErrorActionPreference = "Stop"

Write-Host "Checking DB connection endpoint..."
Write-Host "URL: $Url"

try {
    $response = Invoke-WebRequest -Uri $Url -Method Get -TimeoutSec $TimeoutSec -UseBasicParsing

    $statusCode = [int]$response.StatusCode
    $body = "$($response.Content)".Trim()

    if ($statusCode -lt 200 -or $statusCode -ge 300) {
        Write-Host "FAIL: HTTP $statusCode"
        if ($body) {
            Write-Host "Response body:"
            Write-Host $body
        }
        exit 1
    }

    if ([string]::IsNullOrWhiteSpace($body)) {
        Write-Host "FAIL: Endpoint returned an empty body."
        exit 1
    }

    Write-Host "PASS: Endpoint returned HTTP $statusCode with non-empty content."
    Write-Host "Response body:"
    Write-Host $body
    exit 0
}
catch {
    Write-Host "FAIL: Request error"
    Write-Host $_.Exception.Message

    if ($_.ErrorDetails -and $_.ErrorDetails.Message) {
        Write-Host "Error details:"
        Write-Host $_.ErrorDetails.Message
    }

    exit 1
}
