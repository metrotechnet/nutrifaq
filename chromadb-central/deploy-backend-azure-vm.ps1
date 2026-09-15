param(
    [string]$ResourceGroup,
    [string]$VmName,
    [string]$VmUser,
    [string]$Location,
    [string]$VmSize,
    [string]$ServiceName,
    [int]$ServicePort,
    [string]$RemoteAppDir,
    [switch]$ProvisionVm,
    [switch]$SkipKnowledgeBase,
    [switch]$SkipOpenPort
)

$ErrorActionPreference = "Stop"

function Get-DotEnvValue {
    param(
        [Parameter(Mandatory = $true)]
        [string]$FilePath,
        [Parameter(Mandatory = $true)]
        [string]$Key
    )

    if (-not (Test-Path -LiteralPath $FilePath)) {
        return $null
    }

    $line = Get-Content -LiteralPath $FilePath |
        Where-Object { $_ -match "^\s*$Key\s*=" } |
        Select-Object -First 1

    if (-not $line) {
        return $null
    }

    $value = $line -replace "^\s*$Key\s*=\s*", ""
    $value = $value.Trim()

    if (($value.StartsWith('"') -and $value.EndsWith('"')) -or ($value.StartsWith("'") -and $value.EndsWith("'"))) {
        $value = $value.Substring(1, $value.Length - 2)
    }

    return $value
}

Write-Host "== ChromaDB Central Azure VM deployment =="

$repoRoot = Split-Path -Parent $PSCommandPath
$envFile = Join-Path $repoRoot ".env"

if (-not (Test-Path -LiteralPath $envFile)) {
    throw ".env file not found at $envFile"
}

$defaultResourceGroup = Get-DotEnvValue -FilePath $envFile -Key "AZURE_RESOURCE_GROUP"
$defaultVmName = Get-DotEnvValue -FilePath $envFile -Key "AZURE_VM_NAME"
$defaultVmUser = Get-DotEnvValue -FilePath $envFile -Key "AZURE_VM_USER"
$defaultLocation = Get-DotEnvValue -FilePath $envFile -Key "AZURE_LOCATION"
$defaultVmSize = Get-DotEnvValue -FilePath $envFile -Key "AZURE_VM_SIZE"
$defaultServiceName = Get-DotEnvValue -FilePath $envFile -Key "AZURE_SERVICE_NAME"
$defaultServicePort = Get-DotEnvValue -FilePath $envFile -Key "AZURE_SERVICE_PORT"
$defaultRemoteAppDir = Get-DotEnvValue -FilePath $envFile -Key "AZURE_REMOTE_APP_DIR"

if ([string]::IsNullOrWhiteSpace($ResourceGroup)) { $ResourceGroup = $defaultResourceGroup }
if ([string]::IsNullOrWhiteSpace($VmName)) { $VmName = $defaultVmName }
if ([string]::IsNullOrWhiteSpace($VmUser)) { $VmUser = $defaultVmUser }
if ([string]::IsNullOrWhiteSpace($Location)) { $Location = if ($defaultLocation) { $defaultLocation } else { "eastus" } }
if ([string]::IsNullOrWhiteSpace($VmSize)) { $VmSize = if ($defaultVmSize) { $defaultVmSize } else { "Standard_B2s" } }
if ([string]::IsNullOrWhiteSpace($ServiceName)) { $ServiceName = if ($defaultServiceName) { $defaultServiceName } else { "chromadb-central" } }
if ($ServicePort -le 0) {
    $parsedServicePort = 0
    if ($defaultServicePort -and [int]::TryParse($defaultServicePort, [ref]$parsedServicePort)) {
        $ServicePort = $parsedServicePort
    } else {
        $ServicePort = 2000
    }
}
if ([string]::IsNullOrWhiteSpace($RemoteAppDir)) { $RemoteAppDir = if ($defaultRemoteAppDir) { $defaultRemoteAppDir } else { "/opt/chromadb-central" } }

if ([string]::IsNullOrWhiteSpace($ResourceGroup)) {
    throw "Missing Azure resource group. Set AZURE_RESOURCE_GROUP in .env or pass -ResourceGroup."
}
if ([string]::IsNullOrWhiteSpace($VmName)) {
    throw "Missing VM name. Set AZURE_VM_NAME in .env or pass -VmName."
}
if ([string]::IsNullOrWhiteSpace($VmUser)) {
    throw "Missing VM user. Set AZURE_VM_USER in .env or pass -VmUser."
}
if ($VmUser -match "@") {
    throw "AZURE_VM_USER must be a Linux username (for example: azureuser), not an email address."
}

$azCmd = Get-Command az -ErrorAction SilentlyContinue
if (-not $azCmd) {
    throw "Azure CLI (az) is not installed or not on PATH."
}

Write-Host "Resource group: $ResourceGroup"
Write-Host "VM name:        $VmName"
Write-Host "VM user:        $VmUser"
Write-Host "Location:       $Location"
Write-Host "VM size:        $VmSize"
Write-Host "Service name:   $ServiceName"
Write-Host "Service port:   $ServicePort"
Write-Host "Remote app dir: $RemoteAppDir"

$rgExists = (az group exists --name $ResourceGroup -o tsv).Trim().ToLowerInvariant()

if ($rgExists -ne "true" -and -not $ProvisionVm) {
    throw "Resource group '$ResourceGroup' not found. Re-run with -ProvisionVm to create it."
}

if ($rgExists -ne "true" -and $ProvisionVm) {
    Write-Host "Creating resource group '$ResourceGroup'..."
    az group create --name $ResourceGroup --location $Location | Out-Null
    $rgExists = "true"
}

$vmCount = 0
if ($rgExists -eq "true") {
    $vmCountText = az vm list --resource-group $ResourceGroup --query "[?name=='$VmName'] | length(@)" -o tsv
    if (-not [int]::TryParse($vmCountText, [ref]$vmCount)) {
        throw "Failed to determine whether VM '$VmName' exists in '$ResourceGroup'."
    }
}

$vmExists = ($vmCount -gt 0)

if (-not $vmExists) {
    if (-not $ProvisionVm) {
        throw "VM '$VmName' not found in '$ResourceGroup'. Re-run with -ProvisionVm to create it."
    }

    Write-Host "Creating VM '$VmName'..."
    az vm create --resource-group $ResourceGroup --name $VmName --image Ubuntu2204 --admin-username $VmUser --size $VmSize --generate-ssh-keys | Out-Null
}

if (-not $SkipOpenPort) {
    Write-Host "Opening port $ServicePort on VM NSG..."
    az vm open-port --resource-group $ResourceGroup --name $VmName --port $ServicePort --priority 1001 | Out-Null
}

Write-Host "Preparing deploy archive..."
$stagingDir = Join-Path $env:TEMP ("chromadb-central-deploy-" + [guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Path $stagingDir | Out-Null

$itemsToCopy = @("api", "app.py", "requirements.txt", ".env")
if (-not $SkipKnowledgeBase) {
    $itemsToCopy += "knowledge-base"
}

foreach ($item in $itemsToCopy) {
    $sourcePath = Join-Path $repoRoot $item
    if (-not (Test-Path -LiteralPath $sourcePath)) {
        if ($item -eq "knowledge-base" -and $SkipKnowledgeBase) {
            continue
        }
        throw "Required path missing for deployment: $sourcePath"
    }
    Copy-Item -LiteralPath $sourcePath -Destination (Join-Path $stagingDir $item) -Recurse -Force
}

$zipPath = Join-Path $env:TEMP ("chromadb-central-" + (Get-Date -Format "yyyyMMdd-HHmmss") + ".zip")
if (Test-Path -LiteralPath $zipPath) {
    Remove-Item -LiteralPath $zipPath -Force
}
Compress-Archive -Path (Join-Path $stagingDir "*") -DestinationPath $zipPath -Force

$remoteZip = "/home/$VmUser/chromadb-central.zip"
$publicIp = az vm show -d --resource-group $ResourceGroup --name $VmName --query "publicIps" -o tsv

if ([string]::IsNullOrWhiteSpace($publicIp)) {
    throw "VM '$VmName' does not have a public IP. Cannot upload archive with scp."
}

$scpCmd = Get-Command scp -ErrorAction SilentlyContinue
if (-not $scpCmd) {
    throw "OpenSSH scp is not installed or not on PATH. Install Windows OpenSSH Client and retry."
}

Write-Host "Uploading archive to VM..."
& $scpCmd.Source -o StrictHostKeyChecking=accept-new -o ConnectTimeout=30 $zipPath "$VmUser@$publicIp`:$remoteZip" | Out-Null
if ($LASTEXITCODE -ne 0) {
    throw "scp upload failed. Ensure SSH (port 22) is reachable and your SSH key is authorized for $VmUser@$publicIp."
}

$linuxCommands = @(
    "set -eux",
    "sudo apt-get update",
    "sudo apt-get install -y python3 python3-venv python3-pip unzip",
    "sudo mkdir -p $RemoteAppDir",
    "sudo chown -R ${VmUser}:$VmUser $RemoteAppDir",
    "rm -rf $RemoteAppDir/*",
    "unzip -o $remoteZip -d $RemoteAppDir",
    "cd $RemoteAppDir",
    "python3 -m venv .venv",
    ". .venv/bin/activate",
    "if [ ! -x $RemoteAppDir/.venv/bin/python3 ]; then echo 'Missing executable: $RemoteAppDir/.venv/bin/python3'; ls -la $RemoteAppDir/.venv/bin || true; exit 1; fi",
    "if [ ! -x $RemoteAppDir/.venv/bin/python ] && [ -x $RemoteAppDir/.venv/bin/python3 ]; then ln -sf $RemoteAppDir/.venv/bin/python3 $RemoteAppDir/.venv/bin/python; fi",
    "pip install --upgrade pip",
    "pip install -r requirements.txt",
    "sudo tee /etc/systemd/system/$ServiceName.service > /dev/null << 'EOF'",
    "[Unit]",
    "Description=ChromaDB Central FastAPI service",
    "After=network.target",
    "",
    "[Service]",
    "Type=simple",
    "User=$VmUser",
    "WorkingDirectory=$RemoteAppDir",
    "EnvironmentFile=$RemoteAppDir/.env",
    "Environment=PORT=$ServicePort",
    "ExecStart=$RemoteAppDir/.venv/bin/python3 -m uvicorn app:app --host 0.0.0.0 --port $ServicePort",
    "Restart=always",
    "RestartSec=5",
    "",
    "[Install]",
    "WantedBy=multi-user.target",
    "EOF",
    "sudo systemctl daemon-reload",
    "sudo systemctl enable $ServiceName",
    "if sudo systemctl cat $ServiceName > /dev/null 2>&1; then ACTIVE_SERVICE=$ServiceName; elif sudo systemctl cat ${ServiceName}-service > /dev/null 2>&1; then ACTIVE_SERVICE=${ServiceName}-service; else echo 'Service unit not found. Tried: $ServiceName and ${ServiceName}-service'; sudo systemctl list-unit-files --type=service | grep -i chroma || true; exit 1; fi",
    "echo Using service unit: $ACTIVE_SERVICE",
    "sudo systemctl restart $ACTIVE_SERVICE",
    "sudo systemctl --no-pager --full status $ACTIVE_SERVICE"
)

Write-Host "Linux commands to execute on VM:"
for ($i = 0; $i -lt $linuxCommands.Count; $i++) {
    Write-Host (("[{0:D2}] {1}" -f ($i + 1), $linuxCommands[$i]))
}

Write-Host "Configuring and starting service on VM..."
$runResultJson = az vm run-command invoke --resource-group $ResourceGroup --name $VmName --command-id RunShellScript --scripts $linuxCommands --query "value[0].{status:displayStatus,message:message}" -o json
if ($LASTEXITCODE -ne 0) {
    throw "az vm run-command invoke failed."
}

$runResult = $runResultJson | ConvertFrom-Json
Write-Host "VM run-command status: $($runResult.status)"
Write-Host $runResult.message

if ($runResult.message -match "exit status=([-0-9]+)") {
    $remoteExitCode = [int]$matches[1]
    if ($remoteExitCode -ne 0) {
        throw "Remote Linux commands failed with exit status=$remoteExitCode."
    }
}

Write-Host ""
Write-Host "Deployment complete."
if (-not [string]::IsNullOrWhiteSpace($publicIp)) {
    Write-Host "Service URL: http://$publicIp`:$ServicePort"
    Write-Host "Health URL:  http://$publicIp`:$ServicePort/health"
} else {
    Write-Host "VM has no public IP. Use private networking or a load balancer to reach the service."
}

if (Test-Path -LiteralPath $stagingDir) {
    Remove-Item -LiteralPath $stagingDir -Recurse -Force
}
if (Test-Path -LiteralPath $zipPath) {
    Remove-Item -LiteralPath $zipPath -Force
}