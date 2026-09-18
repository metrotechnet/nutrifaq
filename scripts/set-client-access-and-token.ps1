param(
    [string]$ApiBase = "https://nutrifaq-webapp.azurewebsites.net",
    # [string]$ApiBase = "http://localhost:8080",
    [string]$ResourceGroup = "nutrifaq-rg",
    [string]$AppName = "nutrifaq-webapp",
    [string]$ClientEmail = "denis@imxtech.ca",
    [string]$TenantId = "d3e9806e-79b8-4a79-8fcf-0e55f0241725",
    [string]$AdminToken = "",
    [string]$InitialPassword = "P@ssw0rd!2026",
    [switch]$SkipRoleAssignment,
    [switch]$SkipUserCreation
)

$ErrorActionPreference = "Stop"

function ConvertFrom-Base64UrlJson {
    param([Parameter(Mandatory = $true)][string]$Segment)

    $padded = $Segment.Replace('-', '+').Replace('_', '/')
    switch ($padded.Length % 4) {
        2 { $padded += "==" }
        3 { $padded += "=" }
    }

    $bytes = [Convert]::FromBase64String($padded)
    $json = [Text.Encoding]::UTF8.GetString($bytes)
    return $json | ConvertFrom-Json
}

function Resolve-AppSetting {
    param(
        [Parameter(Mandatory = $true)][string]$Name,
        [Parameter(Mandatory = $true)][array]$Settings
    )

    $entry = $Settings | Where-Object { $_.name -eq $Name } | Select-Object -First 1
    if ($null -eq $entry) {
        return ""
    }
    return "$($entry.value)"
}

function Resolve-ApiScope {
    param(
        [Parameter(Mandatory = $true)][array]$Settings,
        [string]$FallbackTenantId = ""
    )

    $tenantId = Resolve-AppSetting -Name "ENTRA_TENANT_ID" -Settings $Settings
    $audience = Resolve-AppSetting -Name "ENTRA_AUDIENCE" -Settings $Settings
    $clientId = Resolve-AppSetting -Name "ENTRA_CLIENT_ID" -Settings $Settings

    if ([string]::IsNullOrWhiteSpace($tenantId)) {
        $tenantId = $FallbackTenantId
    }

    if ([string]::IsNullOrWhiteSpace($tenantId)) {
        throw "ENTRA_TENANT_ID is missing in App Settings."
    }

    if ([string]::IsNullOrWhiteSpace($audience)) {
        $audience = $clientId
    }

    if ([string]::IsNullOrWhiteSpace($audience)) {
        throw "ENTRA_AUDIENCE and ENTRA_CLIENT_ID are both missing in App Settings."
    }

    $explicitScope = Resolve-AppSetting -Name "ENTRA_TOKEN_SCOPE" -Settings $Settings
    $primaryAudience = ($audience -split ',')[0].Trim()
    if (-not $primaryAudience.StartsWith("api://")) {
        $primaryAudience = "api://$primaryAudience"
    }

    $scopes = @()
    if (-not [string]::IsNullOrWhiteSpace($explicitScope)) {
        $scopes += $explicitScope.Trim()
    }
    $scopes += "$primaryAudience/.default"
    $scopes += "$primaryAudience/access_as_user"

    $uniqueScopes = $scopes | Where-Object { -not [string]::IsNullOrWhiteSpace($_) } | Select-Object -Unique
    return [pscustomobject]@{
        TenantId = $tenantId
        Audience = $primaryAudience
        Scopes = $uniqueScopes
    }
}

function Try-Resolve-AdminToken {
    param(
        [Parameter(Mandatory = $true)][string[]]$Scopes,
        [Parameter(Mandatory = $true)][string]$TenantId
    )

    foreach ($scope in $Scopes) {
        try {
            $token = az account get-access-token --scope $scope --tenant $TenantId --query accessToken -o tsv --only-show-errors 2>$null
            if (-not [string]::IsNullOrWhiteSpace($token)) {
                return [pscustomobject]@{
                    Token = $token.Trim()
                    Scope = $scope
                }
            }
        }
        catch {
            # Continue to the next candidate scope.
        }
    }

    return [pscustomobject]@{
        Token = ""
        Scope = ""
    }
}

function Is-DemoModeEnabled {
    param(
        [Parameter(Mandatory = $true)][array]$Settings
    )

    $raw = Resolve-AppSetting -Name "DEMO_MODE" -Settings $Settings
    if ([string]::IsNullOrWhiteSpace($raw)) {
        return $false
    }

    $normalized = $raw.Trim().ToLowerInvariant()
    return @("1", "true", "yes", "on") -contains $normalized
}

Write-Host "== Configure API client access + token ==" -ForegroundColor Cyan

$azCmd = Get-Command az -ErrorAction SilentlyContinue
if (-not $azCmd) {
    throw "Azure CLI is not installed or not available in PATH."
}

Write-Host "Reading backend app settings to get the expected Entra tenant..." -ForegroundColor Cyan
$settingsJson = az webapp config appsettings list -g $ResourceGroup -n $AppName -o json --only-show-errors
if (-not $settingsJson) {
    throw "Unable to read app settings for $AppName in $ResourceGroup."
}
$settings = $settingsJson | ConvertFrom-Json

if ([string]::IsNullOrWhiteSpace($TenantId)) {
    $TenantId = Resolve-AppSetting -Name "ENTRA_TENANT_ID" -Settings $settings
}
if ([string]::IsNullOrWhiteSpace($TenantId)) {
    throw "ENTRA_TENANT_ID is missing in App Settings. Pass -TenantId explicitly if needed."
}

$apiScopeInfo = Resolve-ApiScope -Settings $settings -FallbackTenantId $TenantId
$TenantId = $apiScopeInfo.TenantId
$tokenScopes = @($apiScopeInfo.Scopes)
$tokenScope = $tokenScopes[0]
$demoModeEnabled = Is-DemoModeEnabled -Settings $settings

az account show | Out-Null
if ($LASTEXITCODE -ne 0) {
    Write-Host "Not logged in Azure CLI for tenant $TenantId. Starting device login..." -ForegroundColor Yellow
    az login --tenant $TenantId --use-device-code --allow-no-subscriptions | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw "Azure login failed for tenant $TenantId."
    }
}
else {
    $currentTenant = az account show --query tenantId -o tsv --only-show-errors
    if (-not [string]::IsNullOrWhiteSpace($currentTenant) -and $currentTenant -ne $TenantId) {
        Write-Host "Current Azure CLI tenant is '$currentTenant' but app expects '$TenantId'. Switching to the expected tenant..." -ForegroundColor Yellow
        az logout | Out-Null
        az login --tenant $TenantId --use-device-code --allow-no-subscriptions | Out-Null
        if ($LASTEXITCODE -ne 0) {
            throw "Azure login failed for tenant $TenantId."
        }
    }
}

if (-not $SkipUserCreation) {
    Write-Host "Creating or ensuring user via backend API..." -ForegroundColor Cyan
    $authHeaderValue = ""

    if ([string]::IsNullOrWhiteSpace($AdminToken)) {
        $adminTokenResult = Try-Resolve-AdminToken -Scopes $tokenScopes -TenantId $TenantId
        $AdminToken = $adminTokenResult.Token
        if (-not [string]::IsNullOrWhiteSpace($adminTokenResult.Scope)) {
            $tokenScope = $adminTokenResult.Scope
        }
    }

    if ([string]::IsNullOrWhiteSpace($AdminToken) -and -not $demoModeEnabled) {
        $scopeList = ($tokenScopes -join "', '")
        throw "An admin bearer token is required to call POST $ApiBase/api/users. Azure CLI could not issue a token for any configured scope. Tried: '$scopeList'. Ensure Expose an API has an enabled delegated scope (for example access_as_user), then run: az logout ; az login --tenant '$TenantId' --scope '$($tokenScopes[-1])', or pass -AdminToken <token>."
    }

    if ([string]::IsNullOrWhiteSpace($AdminToken) -and $demoModeEnabled) {
        Write-Host "DEMO_MODE is enabled. Calling /api/users without Authorization header." -ForegroundColor Yellow
    }
    else {
        $authHeaderValue = "Bearer $AdminToken"
    }

    $headers = @{
        "Content-Type" = "application/json"
    }
    if (-not [string]::IsNullOrWhiteSpace($authHeaderValue)) {
        $headers["Authorization"] = $authHeaderValue
    }

    $displayName = ($ClientEmail.Split('@')[0]).Replace('.', ' ').Replace('_', ' ')
    $createBody = @{
        email = $ClientEmail
        display_name = $displayName
        password = $InitialPassword
        role = "client"
    } | ConvertTo-Json

    $createUrl = "$ApiBase/api/users"
    try {
        $createResponse = Invoke-RestMethod -Method Post -Uri $createUrl -Headers $headers -Body $createBody
        $clientObjectId = $createResponse.user.object_id
        Write-Host "User created/ensured through API; object_id: $clientObjectId" -ForegroundColor Green
    }
    catch {
        $statusCode = $null
        if ($_.Exception.Response -and $_.Exception.Response.StatusCode) {
            $statusCode = [int]$_.Exception.Response.StatusCode
        }
        if ($statusCode -eq 405) {
            throw "POST $createUrl returned 405 Method Not Allowed. The deployed backend does not expose create_user yet (currently /api/users allows GET only). Deploy the latest backend code from api/routes/users.py containing @router.post('/api/users'), then rerun this script."
        }
        throw "User creation via API failed for '$ClientEmail' at $createUrl. Details: $($_.Exception.Message)"
    }

    if (-not $SkipRoleAssignment) {
        Write-Host "Role assignment already handled by the API create endpoint." -ForegroundColor Green
    }
    else {
        Write-Host "Skipping role assignment as requested." -ForegroundColor Yellow
    }
}
else {
    Write-Host "Skipping user creation as requested." -ForegroundColor Yellow
    if (-not $SkipRoleAssignment) {
        Write-Host "Role assignment is skipped because user creation is disabled." -ForegroundColor Yellow
    }
}

Write-Host "Reading backend app settings to compute token scope..." -ForegroundColor Cyan

$scope = $tokenScope
if ([string]::IsNullOrWhiteSpace($scope)) {
    $scope = $tokenScopes[0]
}

Write-Host "Token scope: $scope" -ForegroundColor Cyan
Write-Host "Open device login and authenticate AS the client user: $ClientEmail" -ForegroundColor Yellow
az login --tenant $tenantId --use-device-code --allow-no-subscriptions | Out-Null
if ($LASTEXITCODE -ne 0) {
    throw "Azure login failed for tenant $tenantId."
}

Write-Host "Generating access token..." -ForegroundColor Cyan
$tokenResult = Try-Resolve-AdminToken -Scopes $tokenScopes -TenantId $tenantId
$accessToken = $tokenResult.Token
if (-not [string]::IsNullOrWhiteSpace($tokenResult.Scope)) {
    $scope = $tokenResult.Scope
}
$expiresOn = ""
if (-not [string]::IsNullOrWhiteSpace($accessToken)) {
    $expiresOn = az account get-access-token --scope $scope --query expiresOn -o tsv --only-show-errors
}
if (-not $accessToken) {
    throw "Unable to get access token. Tried scopes: $($tokenScopes -join ', ')."
}

$parts = $accessToken.Split('.')
if ($parts.Count -lt 2) {
    throw "Received invalid JWT format."
}
$claims = ConvertFrom-Base64UrlJson -Segment $parts[1]
$tokenUser = "$($claims.preferred_username)"
if ([string]::IsNullOrWhiteSpace($tokenUser)) {
    $tokenUser = "$($claims.upn)"
}
if ([string]::IsNullOrWhiteSpace($tokenUser)) {
    $tokenUser = "$($claims.email)"
}

if ($tokenUser -and $tokenUser.ToLower() -ne $ClientEmail.ToLower()) {
    Write-Warning "The token appears to belong to '$tokenUser', not '$ClientEmail'."
}

$projectRoot = Split-Path -Parent $PSScriptRoot
$authConfigPath = Join-Path $projectRoot 'example\simple-frontend-chat\auth-config.js'
$tokenLine = 'window.CLIENT_BEARER_TOKEN = "' + $accessToken + '";'
$authConfigContent = [System.String]::Join([Environment]::NewLine, @(
    '// Auto-generated by scripts/set-client-access-and-token.ps1',
    '// Keep this file local. Do not commit real tokens.',
    $tokenLine
))

Set-Content -LiteralPath $authConfigPath -Value $authConfigContent -Encoding UTF8

Write-Host "Token written to: $authConfigPath" -ForegroundColor Green
if ($expiresOn) {
    Write-Host "Token expires on: $expiresOn" -ForegroundColor Green
}
Write-Host "Done." -ForegroundColor Green
