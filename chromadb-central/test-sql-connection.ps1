param(
    [string]$BaseUrl = "",
    [string]$ResourceGroup = "",
    [string]$AppName = "nutrifaq-bd",
    [string]$RootHealthPath = "/health",
    [string]$SqlHealthPath = "/migration/health",
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
            # Fall through to the default host name below.
        }
    }

    return "https://$WebAppName.azurewebsites.net"
}

function Invoke-JsonGet {
    param(
        [string]$Url
    )

    try {
        $response = Invoke-WebRequest -Uri $Url -Method GET -UseBasicParsing
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

Write-Host "Checking deployed API at $BaseUrl" -ForegroundColor Yellow

$rootUrl = ($BaseUrl.TrimEnd("/") + $RootHealthPath)
$sqlUrl = ($BaseUrl.TrimEnd("/") + $SqlHealthPath)

$rootResult = Invoke-JsonGet -Url $rootUrl
$sqlResult = Invoke-JsonGet -Url $sqlUrl

Write-Result -Title "Root health check" -Result $rootResult
Write-Result -Title "SQL health check" -Result $sqlResult

$rootDatabaseOk = $false
if ($rootResult.ok -and $null -ne $rootResult.body -and $rootResult.body.PSObject.Properties.Name -contains "database") {
    $db = $rootResult.body.database
    if ($null -ne $db -and $db.PSObject.Properties.Name -contains "status") {
        $rootDatabaseOk = ($db.status -eq "ok")
    }
}

$sqlOk = $false
if ($sqlResult.ok -and $null -ne $sqlResult.body) {
    if ($sqlResult.body.PSObject.Properties.Name -contains "postgres_connected") {
        $sqlOk = [bool]$sqlResult.body.postgres_connected
    } elseif ($sqlResult.body.PSObject.Properties.Name -contains "status") {
        $sqlOk = ($sqlResult.body.status -eq "ok")
    }
}

Write-Host ""
Write-Host "Summary" -ForegroundColor Cyan
Write-Host "-------" -ForegroundColor Cyan
Write-Host ("Root health reports SQL: {0}" -f $rootDatabaseOk)
Write-Host ("Migration health reports SQL: {0}" -f $sqlOk)

if ($sqlOk) {
    Write-Host "SQL connection looks healthy." -ForegroundColor Green
    exit 0
}

if ($FailOnUnhealthy) {
    Write-Host "SQL connection is not healthy." -ForegroundColor Red
    exit 1
}

Write-Host "SQL connection is not healthy." -ForegroundColor Yellow
exit 1
