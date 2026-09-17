param(
    [string]$BaseUrl = "",
    [string]$ResourceGroup = "",
    [string]$AppName = "nutrifaq-bd",
    [switch]$Test,
    [switch]$Migrate,
    [switch]$Status,
    [string]$Project = "",
    [string]$Collection = "",
    [switch]$FailOnUnhealthy
)

$ErrorActionPreference = "Stop"

function Resolve-AppUrl {
    param(
        [string]$ExplicitBaseUrl,
        [string]$ResourceGroupName,
        [string]$WebAppName
    )

    if (-not [string]::IsNullOrWhiteSpace($ExplicitBaseUrl)) {
        return $ExplicitBaseUrl.TrimEnd("/")
    }

    $az = Get-Command az -ErrorAction SilentlyContinue
    if ($null -ne $az) {
        try {
            if (-not [string]::IsNullOrWhiteSpace($ResourceGroupName)) {
                $appJson = az webapp show --resource-group $ResourceGroupName --name $WebAppName --query "{host:defaultHostName}" -o json --only-show-errors 2>$null
                if ($LASTEXITCODE -eq 0 -and $appJson) {
                    $app = $appJson | ConvertFrom-Json
                    if ($app.host) {
                        return ("https://{0}" -f $app.host)
                    }
                }
            } else {
                $appsJson = az webapp list --query "[?name=='$WebAppName'] | [0].{host:defaultHostName}" -o json --only-show-errors 2>$null
                if ($LASTEXITCODE -eq 0 -and $appsJson) {
                    $app = $appsJson | ConvertFrom-Json
                    if ($app.host) {
                        return ("https://{0}" -f $app.host)
                    }
                }
            }
        } catch {
            # Fall through to default host name below.
        }
    }

    return "https://$WebAppName.azurewebsites.net"
}

function Invoke-JsonRequest {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Url,
        [ValidateSet("GET", "POST")]
        [string]$Method = "GET"
    )

    try {
        $response = Invoke-WebRequest -Uri $Url -Method $Method -UseBasicParsing
        $content = $response.Content
        if ([string]::IsNullOrWhiteSpace($content)) {
            return [pscustomobject]@{
                ok = $true
                statusCode = $response.StatusCode
                url = $Url
                body = $null
                error = $null
            }
        }

        return [pscustomobject]@{
            ok = $true
            statusCode = $response.StatusCode
            url = $Url
            body = ($content | ConvertFrom-Json)
            error = $null
        }
    } catch {
        $statusCode = $null
        $body = $null
        if ($_.Exception.Response -ne $null) {
            $statusCode = $_.Exception.Response.StatusCode.value__
            try {
                $reader = New-Object System.IO.StreamReader($_.Exception.Response.GetResponseStream())
                $raw = $reader.ReadToEnd()
                if (-not [string]::IsNullOrWhiteSpace($raw)) {
                    $body = $raw | ConvertFrom-Json
                }
            } catch {
                $body = $null
            }
        }

        return [pscustomobject]@{
            ok = $false
            statusCode = $statusCode
            url = $Url
            body = $body
            error = $_.Exception.Message
        }
    }
}

function Write-Result {
    param(
        [string]$Title,
        $Result
    )

    Write-Host ""
    Write-Host $Title -ForegroundColor Cyan
    Write-Host ("-" * $Title.Length) -ForegroundColor Cyan
    Write-Host ("URL: {0}" -f $Result.url)
    if ($null -ne $Result.statusCode) {
        Write-Host ("Status code: {0}" -f $Result.statusCode)
    }
    if ($Result.ok) {
        Write-Host "State: OK" -ForegroundColor Green
    } else {
        Write-Host "State: FAILED" -ForegroundColor Red
    }

    if ($null -ne $Result.body) {
        $Result.body | ConvertTo-Json -Depth 10 | Write-Host
    }

    if (-not [string]::IsNullOrWhiteSpace($Result.error)) {
        Write-Host ("Error: {0}" -f $Result.error) -ForegroundColor Red
    }
}

$BaseUrl = Resolve-AppUrl -ExplicitBaseUrl $BaseUrl -ResourceGroupName $ResourceGroup -WebAppName $AppName
$BaseUrl = $BaseUrl.TrimEnd("/")

Write-Host "==============================================================" -ForegroundColor Cyan
Write-Host "PostgreSQL Migration Management Script" -ForegroundColor Cyan
Write-Host "==============================================================" -ForegroundColor Cyan
Write-Host ("Target API: {0}" -f $BaseUrl) -ForegroundColor Yellow

$rootUrl = "$BaseUrl/"
$healthUrl = "$BaseUrl/health"
$statusUrl = "$BaseUrl/migration/status"
$projectsUrl = "$BaseUrl/migration/projects"
$allUrl = "$BaseUrl/migration/migrate-all"
$singleUrl = if ($Project -and $Collection) { "$BaseUrl/migration/migrate/$Project/$Collection" } else { $null }
$migrationHealthUrl = "$BaseUrl/migration/health"

if ($Test) {
    Write-Host "`n[TEST] Checking deployed API endpoints..." -ForegroundColor Cyan
    $rootResult = Invoke-JsonRequest -Url $healthUrl -Method GET
    $migrationHealthResult = Invoke-JsonRequest -Url $migrationHealthUrl -Method GET
    $projectsResult = Invoke-JsonRequest -Url $projectsUrl -Method GET

    Write-Result -Title "Root health check" -Result $rootResult
    Write-Result -Title "Migration health check" -Result $migrationHealthResult
    Write-Result -Title "Projects check" -Result $projectsResult

    $sqlOk = $false
    if ($rootResult.ok -and $rootResult.body -and $rootResult.body.PSObject.Properties.Name -contains "database") {
        $db = $rootResult.body.database
        if ($db -and $db.PSObject.Properties.Name -contains "status") {
            $sqlOk = ($db.status -eq "ok")
        }
    }

    if (-not $sqlOk -and $migrationHealthResult.ok -and $migrationHealthResult.body -and $migrationHealthResult.body.PSObject.Properties.Name -contains "postgres_connected") {
        $sqlOk = [bool]$migrationHealthResult.body.postgres_connected
    }

    Write-Host ""
    Write-Host "Summary" -ForegroundColor Cyan
    Write-Host "-------" -ForegroundColor Cyan
    Write-Host ("SQL connection healthy: {0}" -f $sqlOk)

    if ($sqlOk) {
        exit 0
    }

    if ($FailOnUnhealthy) {
        exit 1
    }

    exit 1
}

if ($Status) {
    Write-Host "`n[STATUS] Querying remote migration status..." -ForegroundColor Cyan
    $statusResult = Invoke-JsonRequest -Url $statusUrl -Method GET
    Write-Result -Title "Migration status" -Result $statusResult
    exit $(if ($statusResult.ok) { 0 } else { 1 })
}

if ($Migrate) {
    Write-Host "`n[RUN] Starting remote full migration..." -ForegroundColor Cyan
    $result = Invoke-JsonRequest -Url $allUrl -Method POST
    Write-Result -Title "Full migration request" -Result $result
    exit $(if ($result.ok) { 0 } else { 1 })
}

if ($singleUrl) {
    Write-Host "`n[RUN] Starting remote migration for $Project/$Collection..." -ForegroundColor Cyan
    $result = Invoke-JsonRequest -Url $singleUrl -Method POST
    Write-Result -Title "Single collection migration request" -Result $result
    exit $(if ($result.ok) { 0 } else { 1 })
}

Write-Host @"
Usage:
  .\migrate-to-postgres.ps1 -Test
  .\migrate-to-postgres.ps1 -Status
  .\migrate-to-postgres.ps1 -Migrate
  .\migrate-to-postgres.ps1 -Project nutria -Collection gdrive_documents

Optional parameters:
  -BaseUrl https://<your-app>.azurewebsites.net
  -ResourceGroup <resource-group-name>
  -AppName nutrifaq-bd
"@ -ForegroundColor Yellow
