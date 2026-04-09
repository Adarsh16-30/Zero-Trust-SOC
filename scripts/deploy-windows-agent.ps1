# deploy-windows-agent.ps1
# This script downloads and installs the Wazuh Agent to collect real telemetry
# from your Windows host and feed it natively into the SOC platform.

param (
    [string]$ManagerIP = "127.0.0.1",
    [string]$AgentName = "SOC-Windows-Host"
)

# Requires Run as Administrator
if (-Not ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole] 'Administrator')) {
    Write-Warning "Please run this script as Administrator to install the agent."
    exit
}

Write-Host "***********************************************" -ForegroundColor Cyan
Write-Host "* Deploying Wazuh Agent for Native SIEM Logging *" -ForegroundColor Cyan
Write-Host "***********************************************" -ForegroundColor Cyan
Write-Host ""

$WazuhVersion = "4.7.0-1"
$InstallerPath = "$env:TEMP\wazuh-agent-$WazuhVersion.msi"
$DownloadUrl = "https://packages.wazuh.com/4.x/windows/wazuh-agent-$WazuhVersion.msi"

if (-Not (Test-Path $InstallerPath)) {
    Write-Host "Downloading Wazuh Agent ($WazuhVersion)..." -ForegroundColor Yellow
    try {
        Invoke-WebRequest -Uri $DownloadUrl -OutFile $InstallerPath -UseBasicParsing | Out-Null
    } catch {
        Write-Error "Failed to download the installer: $_.Exception.Message"
        exit 1
    }
} else {
    Write-Host "Installer already exists at $InstallerPath" -ForegroundColor Green
}

Write-Host "Installing Wazuh Agent and registering to Manager at $ManagerIP..." -ForegroundColor Yellow

$InstallArgs = "/i `"$InstallerPath`" /q WAZUH_MANAGER=`"$ManagerIP`" WAZUH_REGISTRATION_SERVER=`"$ManagerIP`" WAZUH_AGENT_NAME=`"$AgentName`""

try {
    $process = Start-Process -FilePath "msiexec.exe" -ArgumentList $InstallArgs -Wait -NoNewWindow -PassThru
    if ($process.ExitCode -eq 0) {
        Write-Host "Installation successful." -ForegroundColor Green
    } else {
        Write-Warning "msiexec exited with code $($process.ExitCode). Is the agent already installed?"
    }
} catch {
    Write-Error "Installation failed: $_"
    exit 1
}

Write-Host "Starting Wazuh service..." -ForegroundColor Yellow
Start-Service -Name "Wazuh" -ErrorAction SilentlyContinue | Out-Null

Start-Sleep -Seconds 3
if ((Get-Service "Wazuh").Status -eq "Running") {
    Write-Host ""
    Write-Host "[+] Wazuh Agent successfully deployed and running!" -ForegroundColor Green
    Write-Host "Real Windows telemetry (Security logs, Sysmon, etc.) is now flowing into:" -ForegroundColor Cyan
    Write-Host "  -> Wazuh Manager" -ForegroundColor Cyan
    Write-Host "  -> Kafka (via wazuh-kafka-bridge)" -ForegroundColor Cyan
    Write-Host "  -> OpenSearch" -ForegroundColor Cyan
    Write-Host "  -> Anomaly Detection Engine" -ForegroundColor Cyan
} else {
    Write-Host "[!] Failed to start the Wazuh service. Check Windows Services." -ForegroundColor Red
}
