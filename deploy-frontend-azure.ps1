param(
    [string]$ResourceGroup = "nutrifaq-rg",
    [string]$Location = "eastus",
    [string]$StorageAccountName = "nutrifaqfeprod",
    [string]$FrontendDir = "public",
    [string]$BackendUrl = "https://nutrifaq-api-chhpeha3h9ehegft.canadacentral-01.azurewebsites.net",
    [string]$BackendAppName = "nutrifaq-api",
    [switch]$UpdateBackendCors
)

$ErrorActionPreference = "Stop"

Write-Host "== NutriFAQ Frontend Azure Deployment =="

$azCmd = Get-Command az -ErrorAction SilentlyContinue
if (-not $azCmd) {
    throw "Azure CLI (az) is not installed or not on PATH."
}

# Verify we have an Azure session before running provisioning commands.
az account show | Out-Null
if ($LASTEXITCODE -ne 0) {
    throw "Not logged in to Azure. Run 'az login' first."
}

# Ensure Storage provider is available for static website hosting resources.
$storageProviderState = az provider show --namespace Microsoft.Storage --query "registrationState" -o tsv
if ($storageProviderState -ne "Registered") {
    Write-Host "Microsoft.Storage provider state is '$storageProviderState'. Registering..."
    az provider register --namespace Microsoft.Storage | Out-Null
    $storageProviderState = az provider show --namespace Microsoft.Storage --query "registrationState" -o tsv
    if ($storageProviderState -ne "Registered") {
        throw "Microsoft.Storage provider is still '$storageProviderState'. Wait a few minutes and run the script again."
    }
}

if (-not (Test-Path -LiteralPath $FrontendDir)) {
    throw "Frontend directory '$FrontendDir' does not exist."
}

if (-not $StorageAccountName) {
    $suffix = -join ((48..57) | Get-Random -Count 6 | ForEach-Object { [char]$_ })
    $StorageAccountName = ("nutrifaqfe{0}" -f $suffix).ToLower()
}

if ($StorageAccountName.Length -lt 3 -or $StorageAccountName.Length -gt 24 -or $StorageAccountName -notmatch '^[a-z0-9]+$') {
    throw "StorageAccountName must be 3-24 characters and use only lowercase letters and numbers."
}

Write-Host "Ensuring resource group '$ResourceGroup' exists in '$Location'..."
az group create --name $ResourceGroup --location $Location | Out-Null
if ($LASTEXITCODE -ne 0) {
    throw "Failed to ensure resource group '$ResourceGroup'."
}

Write-Host "Ensuring storage account '$StorageAccountName' exists..."
$saCount = az storage account list --resource-group $ResourceGroup --query "[?name=='$StorageAccountName'] | length(@)" -o tsv
if ($saCount -eq "0") {
    az storage account create --name $StorageAccountName --resource-group $ResourceGroup --location $Location --sku Standard_LRS --kind StorageV2 --min-tls-version TLS1_2 --allow-blob-public-access true | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to create storage account '$StorageAccountName'."
    }
}

# Static website endpoint needs public blob access to serve content.
az storage account update --name $StorageAccountName --resource-group $ResourceGroup --allow-blob-public-access true -o none
if ($LASTEXITCODE -ne 0) {
    throw "Failed to enable blob public access on '$StorageAccountName'."
}

Write-Host "Enabling static website hosting..."
az storage blob service-properties update --account-name $StorageAccountName --static-website --index-document index.html --404-document index.html --auth-mode key | Out-Null
if ($LASTEXITCODE -ne 0) {
    throw "Failed to enable static website hosting on '$StorageAccountName'."
}

$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$tempRoot = Join-Path $env:TEMP ("nutrifaq-frontend-{0}" -f $stamp)
New-Item -Path $tempRoot -ItemType Directory | Out-Null

try {
    Write-Host "Preparing frontend artifact from '$FrontendDir'..."
    Copy-Item -Path (Join-Path $FrontendDir "*") -Destination $tempRoot -Recurse -Force

    if ($BackendUrl) {
        $backendConfigDir = Join-Path $tempRoot "static\js"
        New-Item -Path $backendConfigDir -ItemType Directory -Force | Out-Null
        $backendConfigPath = Join-Path $backendConfigDir "backend-url.js"
        "window.BACKEND_URL = '$BackendUrl';" | Set-Content -Path $backendConfigPath -Encoding UTF8
    }

    Write-Host "Uploading frontend files to `$web container..."
    az storage blob upload-batch --account-name $StorageAccountName --auth-mode key --destination '$web' --source $tempRoot --overwrite true | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to upload frontend files to storage account '$StorageAccountName'."
    }

    $frontendUrl = az storage account show --name $StorageAccountName --resource-group $ResourceGroup --query "primaryEndpoints.web" -o tsv
    if (-not $frontendUrl) {
        throw "Unable to resolve frontend URL from storage account."
    }

    Write-Host "Frontend deployed successfully."
    Write-Host "Frontend URL: $frontendUrl"

    if ($UpdateBackendCors) {
        $frontendOrigin = $frontendUrl.TrimEnd('/')
        Write-Host "Updating backend CORS with '$frontendOrigin'..."
        az webapp config appsettings set --resource-group $ResourceGroup --name $BackendAppName --settings "ADDITIONAL_CORS_ORIGINS=$frontendOrigin" | Out-Null
        az webapp restart --resource-group $ResourceGroup --name $BackendAppName | Out-Null
        Write-Host "Backend CORS updated on '$BackendAppName'."
    }
} finally {
    if (Test-Path -LiteralPath $tempRoot) {
        Remove-Item -LiteralPath $tempRoot -Recurse -Force
    }
}
