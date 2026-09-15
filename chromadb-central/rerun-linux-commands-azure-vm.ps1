param(
    [string]$ResourceGroup,
    [string]$VmName,
    [string]$VmUser,
    [string]$ServiceName,
    [int]$ServicePort,
    [string]$RemoteAppDir,
    [string]$RemoteZip,
    [switch]$SkipApt,
    [switch]$SkipPip,
    [switch]$SkipExtract,
    [switch]$SkipWipe,
    [switch]$RestartOnly
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

Write-Host "== Re-run Linux commands on Azure VM (no reload) =="

$repoRoot = Split-Path -Parent $PSCommandPath
$envFile = Join-Path $repoRoot ".env"

if (-not (Test-Path -LiteralPath $envFile)) {
    throw ".env file not found at $envFile"
}

$defaultResourceGroup = Get-DotEnvValue -FilePath $envFile -Key "AZURE_RESOURCE_GROUP"
$defaultVmName = Get-DotEnvValue -FilePath $envFile -Key "AZURE_VM_NAME"
$defaultVmUser = Get-DotEnvValue -FilePath $envFile -Key "AZURE_VM_USER"
$defaultServiceName = Get-DotEnvValue -FilePath $envFile -Key "AZURE_SERVICE_NAME"
$defaultServicePort = Get-DotEnvValue -FilePath $envFile -Key "AZURE_SERVICE_PORT"
$defaultRemoteAppDir = Get-DotEnvValue -FilePath $envFile -Key "AZURE_REMOTE_APP_DIR"

if ([string]::IsNullOrWhiteSpace($ResourceGroup)) { $ResourceGroup = $defaultResourceGroup }
if ([string]::IsNullOrWhiteSpace($VmName)) { $VmName = $defaultVmName }
if ([string]::IsNullOrWhiteSpace($VmUser)) { $VmUser = $defaultVmUser }
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
if ([string]::IsNullOrWhiteSpace($RemoteZip)) { $RemoteZip = "/home/$VmUser/chromadb-central.zip" }

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

$vmCountText = az vm list --resource-group $ResourceGroup --query "[?name=='$VmName'] | length(@)" -o tsv
$vmCount = 0
if (-not [int]::TryParse($vmCountText, [ref]$vmCount) -or $vmCount -eq 0) {
    throw "VM '$VmName' not found in '$ResourceGroup'."
}

Write-Host "Resource group: $ResourceGroup"
Write-Host "VM name:        $VmName"
Write-Host "VM user:        $VmUser"
Write-Host "Service name:   $ServiceName"
Write-Host "Service port:   $ServicePort"
Write-Host "Remote app dir: $RemoteAppDir"
Write-Host "Remote zip:     $RemoteZip"

$linuxCommands = @("set -eux")

if (-not $RestartOnly) {
    if (-not $SkipApt) {
        $linuxCommands += "sudo apt-get update"
        $linuxCommands += "sudo apt-get install -y python3 python3-venv python3-pip unzip"
    }

    $linuxCommands += "sudo mkdir -p $RemoteAppDir"
    $linuxCommands += "sudo chown -R ${VmUser}:$VmUser $RemoteAppDir"

    if (-not $SkipWipe) {
        $linuxCommands += "rm -rf $RemoteAppDir/*"
    }

    if (-not $SkipExtract) {
        $linuxCommands += "if [ ! -f $RemoteZip ]; then echo 'Missing archive: $RemoteZip'; exit 1; fi"
        $linuxCommands += "unzip -o $RemoteZip -d $RemoteAppDir"
    }

    $linuxCommands += "cd $RemoteAppDir"
    $linuxCommands += "python3 -m venv .venv"
    $linuxCommands += ". .venv/bin/activate"
    $linuxCommands += "if [ ! -x $RemoteAppDir/.venv/bin/python3 ]; then echo 'Missing executable: $RemoteAppDir/.venv/bin/python3'; ls -la $RemoteAppDir/.venv/bin || true; exit 1; fi"
    $linuxCommands += "if [ ! -x $RemoteAppDir/.venv/bin/python ] && [ -x $RemoteAppDir/.venv/bin/python3 ]; then ln -sf $RemoteAppDir/.venv/bin/python3 $RemoteAppDir/.venv/bin/python; fi"

    if (-not $SkipPip) {
        $linuxCommands += "pip install --upgrade pip"
        $linuxCommands += "pip install -r requirements.txt"
    }

    $linuxCommands += "sudo tee /etc/systemd/system/$ServiceName.service > /dev/null << 'EOF'"
    $linuxCommands += "[Unit]"
    $linuxCommands += "Description=ChromaDB Central FastAPI service"
    $linuxCommands += "After=network.target"
    $linuxCommands += ""
    $linuxCommands += "[Service]"
    $linuxCommands += "Type=simple"
    $linuxCommands += "User=$VmUser"
    $linuxCommands += "WorkingDirectory=$RemoteAppDir"
    $linuxCommands += "EnvironmentFile=$RemoteAppDir/.env"
    $linuxCommands += "Environment=PORT=$ServicePort"
    $linuxCommands += "ExecStart=$RemoteAppDir/.venv/bin/python3 -m uvicorn app:app --host 0.0.0.0 --port $ServicePort"
    $linuxCommands += "Restart=always"
    $linuxCommands += "RestartSec=5"
    $linuxCommands += ""
    $linuxCommands += "[Install]"
    $linuxCommands += "WantedBy=multi-user.target"
    $linuxCommands += "EOF"
    $linuxCommands += "sudo systemctl daemon-reload"
    $linuxCommands += "sudo systemctl enable $ServiceName"
}

$linuxCommands += "if sudo systemctl cat $ServiceName > /dev/null 2>&1; then ACTIVE_SERVICE=$ServiceName; elif sudo systemctl cat ${ServiceName}-service > /dev/null 2>&1; then ACTIVE_SERVICE=${ServiceName}-service; else echo 'Service unit not found. Tried: $ServiceName and ${ServiceName}-service'; sudo systemctl list-unit-files --type=service | grep -i chroma || true; exit 1; fi"
$linuxCommands += "echo Using service unit: $ACTIVE_SERVICE"
$linuxCommands += "sudo systemctl restart $ACTIVE_SERVICE"
$linuxCommands += "sudo systemctl --no-pager --full status $ACTIVE_SERVICE"

Write-Host "Linux commands to execute on VM:"
for ($i = 0; $i -lt $linuxCommands.Count; $i++) {
    Write-Host (("[{0:D2}] {1}" -f ($i + 1), $linuxCommands[$i]))
}

Write-Host "Running remote Linux commands (no app files are copied)..."
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

Write-Host "Done. Linux commands completed on VM."