param(
    [string]$EnvPath = ".env",
    [string]$AppName = "",
    [string]$ResourceGroup = "",
    [string]$ZipArtifactPath = ""
)

$ErrorActionPreference = "Stop"

function Get-DotEnvMap {
    param([string]$Path)

    $map = @{}
    if (-not (Test-Path -LiteralPath $Path)) {
        throw ".env file not found at '$Path'."
    }

    foreach ($line in Get-Content -LiteralPath $Path) {
        $trimmed = $line.Trim()
        if ([string]::IsNullOrWhiteSpace($trimmed) -or $trimmed.StartsWith("#")) {
            continue
        }

        $sep = $trimmed.IndexOf("=")
        if ($sep -le 0) {
            continue
        }

        $key = $trimmed.Substring(0, $sep).Trim()
        $value = $trimmed.Substring($sep + 1)
        if ($key) {
            $map[$key] = $value
        }
    }

    return $map
}

function Resolve-AppNameFromBackendUrl {
    param([hashtable]$DotEnvMap)

    $backendUrl = [string]$DotEnvMap["BACKEND_URL"]
    if ([string]::IsNullOrWhiteSpace($backendUrl)) {
        throw "BACKEND_URL is required in .env when -AppName is not provided."
    }

    try {
        $uri = [Uri]$backendUrl
    } catch {
        throw "BACKEND_URL is not a valid URL: '$backendUrl'"
    }

    $resolved = $uri.Host -replace "\.azurewebsites\.net$", ""
    if ([string]::IsNullOrWhiteSpace($resolved)) {
        throw "Unable to resolve App Service name from BACKEND_URL '$backendUrl'."
    }

    return $resolved
}

function Resolve-AppVersionFromZip {
    param([string]$ZipPath)

    $timestamp = ""
    if (-not [string]::IsNullOrWhiteSpace($ZipPath)) {
        if (-not (Test-Path -LiteralPath $ZipPath)) {
            throw "Zip artifact not found at '$ZipPath'."
        }
        $zipName = [System.IO.Path]::GetFileName($ZipPath)
        $zipMatch = [regex]::Match($zipName, "(\d{8}-\d{6})")
        if ($zipMatch.Success) {
            $timestamp = $zipMatch.Groups[1].Value
        }
    } else {
        $searchRoot = (Resolve-Path ".").Path
        $candidate = Get-ChildItem -LiteralPath $searchRoot -Filter "*.zip" -File |
            Sort-Object LastWriteTime -Descending |
            Select-Object -First 1
        if ($candidate) {
            $zipMatch = [regex]::Match($candidate.Name, "(\d{8}-\d{6})")
            if ($zipMatch.Success) {
                $timestamp = $zipMatch.Groups[1].Value
            }
        }
    }

    if ([string]::IsNullOrWhiteSpace($timestamp)) {
        $timestamp = (Get-Date -Format "yyyyMMdd-HHmmss")
    }
    return "az-$timestamp"
}

if (-not (Get-Command az -ErrorAction SilentlyContinue)) {
    throw "Azure CLI (az) is required but was not found in PATH."
}

$dotEnvMap = Get-DotEnvMap -Path $EnvPath
$dotEnvMap["APP_VERSION"] = Resolve-AppVersionFromZip -ZipPath $ZipArtifactPath

if ([string]::IsNullOrWhiteSpace($AppName)) {
    $AppName = Resolve-AppNameFromBackendUrl -DotEnvMap $dotEnvMap
}

if ([string]::IsNullOrWhiteSpace($ResourceGroup)) {
    $ResourceGroup = az webapp list --query "[?name=='$AppName'].resourceGroup | [0]" -o tsv --only-show-errors
    if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($ResourceGroup)) {
        throw "Unable to resolve resource group for app '$AppName'. Pass -ResourceGroup explicitly."
    }
}

$settingsArgs = @()
foreach ($entry in $dotEnvMap.GetEnumerator()) {
    $settingsArgs += ("{0}={1}" -f $entry.Key, $entry.Value)
}

if ($settingsArgs.Count -eq 0) {
    throw "No settings were found in '$EnvPath'."
}

Write-Host "Pushing $($settingsArgs.Count) app settings from '$EnvPath' to app '$AppName' (rg='$ResourceGroup')..."
Write-Host "Resolved APP_VERSION: $($dotEnvMap["APP_VERSION"])"
az webapp config appsettings set `
    --resource-group $ResourceGroup `
    --name $AppName `
    --settings $settingsArgs `
    --only-show-errors | Out-Null

if ($LASTEXITCODE -ne 0) {
    throw "Failed to push app settings."
}

Write-Host "Done. Environment settings updated without deploying code."
