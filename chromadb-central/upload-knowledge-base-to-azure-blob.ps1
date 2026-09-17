param(
    [string]$StorageAccountName = "",
    [string]$StorageAccountKey = "",
    [string]$ContainerName = "nutrifaq-knowledge-base",
    [string]$ResourceGroup = "",
    [string]$SourceFolder = "knowledge-base",
    [switch]$CreateContainer,
    [switch]$AuthModeLogin
)

$ErrorActionPreference = "Stop"

function Resolve-StorageAccountName {
    param(
        [string]$ExplicitName,
        [string]$ResourceGroupName
    )

    if (-not [string]::IsNullOrWhiteSpace($ExplicitName)) {
        return $ExplicitName
    }

    if (-not [string]::IsNullOrWhiteSpace($ResourceGroupName)) {
        $accountsJson = az storage account list --resource-group $ResourceGroupName --query "[0].name" -o json --only-show-errors 2>$null
        if ($LASTEXITCODE -eq 0 -and $accountsJson) {
            $accountName = $accountsJson | ConvertFrom-Json
            if ($accountName) {
                return $accountName
            }
        }
    }

    return ""
}

function Assert-CommandExists {
    param([string]$CommandName)
    $cmd = Get-Command $CommandName -ErrorAction SilentlyContinue
    if (-not $cmd) {
        throw "$CommandName is not installed or not on PATH."
    }
}

Assert-CommandExists -CommandName "az"

$storageAccountName = Resolve-StorageAccountName -ExplicitName $StorageAccountName -ResourceGroupName $ResourceGroup
if ([string]::IsNullOrWhiteSpace($storageAccountName)) {
    throw "Storage account name was not provided and could not be resolved from the resource group."
}

if (-not (Test-Path -LiteralPath $SourceFolder)) {
    throw "Source folder '$SourceFolder' was not found."
}

Write-Host "==============================================================" -ForegroundColor Cyan
Write-Host "Knowledge-base Azure Blob Upload" -ForegroundColor Cyan
Write-Host "==============================================================" -ForegroundColor Cyan
Write-Host ("Source folder: {0}" -f (Resolve-Path -LiteralPath $SourceFolder).Path)
Write-Host ("Storage account: {0}" -f $storageAccountName)
Write-Host ("Container: {0}" -f $ContainerName)
if (-not [string]::IsNullOrWhiteSpace($StorageAccountKey)) {
    Write-Host "Auth mode: key (provided storage account key)"
} elseif ($AuthModeLogin) {
    Write-Host "Auth mode: login"
} else {
    Write-Host "Auth mode: account key lookup required for container operations"
}

if ($CreateContainer) {
    Write-Host "Ensuring container exists..."
    if ($AuthModeLogin) {
        az storage container create --account-name $storageAccountName --name $ContainerName --auth-mode login --only-show-errors | Out-Null
    } elseif (-not [string]::IsNullOrWhiteSpace($StorageAccountKey)) {
        az storage container create --account-name $storageAccountName --name $ContainerName --account-key $StorageAccountKey --only-show-errors | Out-Null
    } else {
        az storage container create --account-name $storageAccountName --name $ContainerName --auth-mode key --only-show-errors | Out-Null
    }
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to create or verify container '$ContainerName'."
    }
}

Write-Host "Uploading knowledge-base to Azure Blob Storage..."
if ($AuthModeLogin) {
    az storage blob upload-batch `
        --account-name $storageAccountName `
        --auth-mode login `
        --destination $ContainerName `
        --source $SourceFolder `
        --destination-path knowledge-base `
        --overwrite true `
        --only-show-errors
} elseif (-not [string]::IsNullOrWhiteSpace($StorageAccountKey)) {
    az storage blob upload-batch `
        --account-name $storageAccountName `
        --account-key $StorageAccountKey `
        --destination $ContainerName `
        --source $SourceFolder `
        --destination-path knowledge-base `
        --overwrite true `
        --only-show-errors
} else {
    az storage blob upload-batch `
        --account-name $storageAccountName `
        --auth-mode key `
        --destination $ContainerName `
        --source $SourceFolder `
        --destination-path knowledge-base `
        --overwrite true `
        --only-show-errors
}

if ($LASTEXITCODE -ne 0) {
    throw "Failed to upload '$SourceFolder' to Azure Blob Storage. If login auth is blocked, pass -StorageAccountKey <key> and use key auth."
}

Write-Host "Upload complete." -ForegroundColor Green