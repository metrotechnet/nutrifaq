param(
    [string]$ResourceGroup = "nutrifaq-rg",
    [string]$Location = "eastus",
    [string]$StorageAccountName = "nutrifaqblobstorage",
    [string]$FrontendDir = "public",
    [string]$BackendUrl = "https://nutrifaq-webapp.azurewebsites.net",
    [string]$BackendAppName = "nutrifaq-webapp",
    [string]$QueryAccessKey = "",
    [switch]$CleanWeb,
    [switch]$UpdateBackendCors,
    [switch]$SkipCacheControl
)

$ErrorActionPreference = "Stop"

function Get-DotEnvValue {
    param(
        [Parameter(Mandatory = $true)][string]$FilePath,
        [Parameter(Mandatory = $true)][string]$Key
    )

    if (-not (Test-Path -LiteralPath $FilePath)) {
        return ""
    }

    $line = Get-Content -LiteralPath $FilePath | Where-Object { $_ -match "^$Key=" } | Select-Object -First 1
    if (-not $line) {
        return ""
    }

    $value = ($line -split "=", 2)[1]
    if ($null -eq $value) {
        return ""
    }

    return $value.Trim()
}

function Set-BlobCacheControlByPattern {
    param(
        [Parameter(Mandatory = $true)][string]$AccountName,
        [Parameter(Mandatory = $true)][string]$Pattern,
        [Parameter(Mandatory = $true)][string]$CacheControl
    )

    # Use per-blob updates for broad Azure CLI compatibility.
    $allBlobNames = az storage blob list --account-name $AccountName --container-name '$web' --auth-mode key --query "[].name" -o tsv --only-show-errors 2>$null
    if ($LASTEXITCODE -ne 0 -or -not $allBlobNames) {
        Write-Warning "Could not list blobs for cache-control update."
        return
    }

    $matchingNames = @($allBlobNames -split "`r?`n" | Where-Object { $_ -and ($_ -like $Pattern) })
    if ($matchingNames.Count -eq 0) {
        Write-Host "No blobs matched '$Pattern' for cache-control update."
        return
    }

    $failedNames = @()
    foreach ($blobName in $matchingNames) {
        az storage blob update --account-name $AccountName --container-name '$web' --name $blobName --auth-mode key --content-cache-control $CacheControl --only-show-errors | Out-Null
        if ($LASTEXITCODE -ne 0) {
            $failedNames += $blobName
        }
    }

    if ($failedNames.Count -gt 0) {
        Write-Warning "Cache-control update partially failed for pattern '$Pattern'. Failed blobs: $($failedNames -join ', ')"
    } else {
        Write-Host "Cache-control applied for pattern '$Pattern'."
    }
}

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

$frontendRootDir = (Resolve-Path -LiteralPath $FrontendDir).Path
$rootStaticDir = Join-Path $PSScriptRoot "static"
$frontendStaticDir = Join-Path $frontendRootDir "static"
if (Test-Path -LiteralPath $rootStaticDir) {
    Write-Host "Syncing local static/ to local '$FrontendDir/static'..."
    if (Test-Path -LiteralPath $frontendStaticDir) {
        Remove-Item -LiteralPath $frontendStaticDir -Recurse -Force
    }
    New-Item -Path $frontendStaticDir -ItemType Directory -Force | Out-Null
    Copy-Item -Path (Join-Path $rootStaticDir "*") -Destination $frontendStaticDir -Recurse -Force
} else {
    Write-Warning "Local static folder not found at '$rootStaticDir'. Skipping local public/static sync."
}

if ([string]::IsNullOrWhiteSpace($QueryAccessKey)) {
    $QueryAccessKey = $env:QUERY_ACCESS_KEY
}
if ([string]::IsNullOrWhiteSpace($QueryAccessKey)) {
    $dotEnvPath = Join-Path $PSScriptRoot ".env"
    $QueryAccessKey = Get-DotEnvValue -FilePath $dotEnvPath -Key "QUERY_ACCESS_KEY"
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
$storageAccountResourceGroup = $ResourceGroup
$existingStorageAccountRg = az storage account show --name $StorageAccountName --query "resourceGroup" -o tsv --only-show-errors 2>$null
if ($LASTEXITCODE -eq 0 -and -not [string]::IsNullOrWhiteSpace($existingStorageAccountRg)) {
    $storageAccountResourceGroup = $existingStorageAccountRg.Trim()
    Write-Host "Using existing storage account '$StorageAccountName' in resource group '$storageAccountResourceGroup'."
} else {
    $nameAvailable = az storage account check-name --name $StorageAccountName --query "nameAvailable" -o tsv --only-show-errors
    if ($LASTEXITCODE -ne 0) {
        throw "Unable to validate availability for storage account name '$StorageAccountName'."
    }

    if ($nameAvailable -ne "true") {
        throw "Storage account name '$StorageAccountName' is already taken and not accessible in the current subscription. Use a different -StorageAccountName or switch to the subscription that owns it."
    }

    az storage account create --name $StorageAccountName --resource-group $ResourceGroup --location $Location --sku Standard_LRS --kind StorageV2 --min-tls-version TLS1_2 --allow-blob-public-access true | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to create storage account '$StorageAccountName'."
    }
}

# Static website endpoint needs public blob access to serve content.
az storage account update --name $StorageAccountName --resource-group $storageAccountResourceGroup --allow-blob-public-access true -o none
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

    if (Test-Path -LiteralPath $rootStaticDir) {
        Write-Host "Syncing root static assets into frontend artifact (clean mirror)..."
        $artifactStaticDir = Join-Path $tempRoot "static"

        # Ensure public/static in the artifact is a clean mirror of root static.
        if (Test-Path -LiteralPath $artifactStaticDir) {
            Remove-Item -LiteralPath $artifactStaticDir -Recurse -Force
        }

        New-Item -Path $artifactStaticDir -ItemType Directory -Force | Out-Null
        Copy-Item -Path (Join-Path $rootStaticDir "*") -Destination $artifactStaticDir -Recurse -Force
    }

    if ($BackendUrl) {
        $backendConfigDir = Join-Path $tempRoot "static\js"
        New-Item -Path $backendConfigDir -ItemType Directory -Force | Out-Null
        $backendConfigPath = Join-Path $backendConfigDir "backend-url.js"
        "window.BACKEND_URL = '$BackendUrl';" | Set-Content -Path $backendConfigPath -Encoding UTF8

        $authConfigPath = Join-Path $backendConfigDir "auth-config.js"
        if ([string]::IsNullOrWhiteSpace($QueryAccessKey)) {
            "window.CLIENT_QUERY_KEY = '';" | Set-Content -Path $authConfigPath -Encoding UTF8
        }
        else {
            "window.CLIENT_QUERY_KEY = '$QueryAccessKey';" | Set-Content -Path $authConfigPath -Encoding UTF8
        }
    }

    # Guardrail: ensure critical static folders are present in the artifact before upload.
    $requiredArtifactFolders = @(
        (Join-Path $tempRoot "static\assets"),
        (Join-Path $tempRoot "static\locales")
    )
    foreach ($requiredFolder in $requiredArtifactFolders) {
        if (-not (Test-Path -LiteralPath $requiredFolder)) {
            throw "Missing required folder in frontend artifact: '$requiredFolder'"
        }
    }

    $assetFiles = @(Get-ChildItem -LiteralPath (Join-Path $tempRoot "static\assets") -Recurse -File -ErrorAction SilentlyContinue)
    $localeFiles = @(Get-ChildItem -LiteralPath (Join-Path $tempRoot "static\locales") -Recurse -File -ErrorAction SilentlyContinue)
    if ($assetFiles.Count -eq 0) {
        throw "No files found in artifact static/assets. Deployment aborted to avoid incomplete frontend publish."
    }
    if ($localeFiles.Count -eq 0) {
        throw "No files found in artifact static/locales. Deployment aborted to avoid incomplete frontend publish."
    }

    Write-Host "Artifact check: static/assets files=$($assetFiles.Count), static/locales files=$($localeFiles.Count)"

    if ($CleanWeb) {
        Write-Host "Cleaning `$web container before upload..."
        az storage blob delete-batch --account-name $StorageAccountName --auth-mode key --source '$web' --pattern '*' --only-show-errors | Out-Null
        if ($LASTEXITCODE -ne 0) {
            throw "Failed to clean `$web container on storage account '$StorageAccountName'."
        }
    }

    Write-Host "Uploading frontend files to `$web container..."
    az storage blob upload-batch --account-name $StorageAccountName --auth-mode key --destination '$web' --source $tempRoot --overwrite true | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to upload frontend files to storage account '$StorageAccountName'."
    }

    if ($SkipCacheControl) {
        Write-Host "Skipping cache-control metadata updates (-SkipCacheControl)."
    } else {
        Write-Host "Applying cache-control metadata to reduce stale content..."
        Set-BlobCacheControlByPattern -AccountName $StorageAccountName -Pattern "*.html" -CacheControl "no-cache, no-store, must-revalidate"
        Set-BlobCacheControlByPattern -AccountName $StorageAccountName -Pattern "*.json" -CacheControl "no-cache, must-revalidate"
        Set-BlobCacheControlByPattern -AccountName $StorageAccountName -Pattern "*.js" -CacheControl "public, max-age=300"
        Set-BlobCacheControlByPattern -AccountName $StorageAccountName -Pattern "*.css" -CacheControl "public, max-age=300"
    }

    $frontendUrl = az storage account show --name $StorageAccountName --resource-group $storageAccountResourceGroup --query "primaryEndpoints.web" -o tsv
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
