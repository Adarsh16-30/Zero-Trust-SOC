# Wazuh Agent Installer for Windows
# Usage: .\install_wazuh_agent.ps1 -ManagerIP "YOUR_MANAGER_IP"

Param(
    [string]$ManagerIP = "localhost"
)

$ErrorActionPreference = "Stop"

Write-Host "Starting Wazuh Agent Installation..." -ForegroundColor Cyan
Write-Host "Target Manager: $ManagerIP"

# Download the MSI
$Url = "https://packages.wazuh.com/4.x/windows/wazuh-agent-4.7.0-1.msi"
$Output = "$env:TEMP\wazuh-agent.msi"

Write-Host "Downloading agent package..."
Invoke-WebRequest -Uri $Url -OutFile $Output

# Install with Manager IP
Write-Host "Installing MSI (this may require elevation)..."
$Arguments = "/i `"$Output`" /quiet WAZUH_MANAGER=`"$ManagerIP`""
Start-Process msiexec.exe -ArgumentList $Arguments -Wait

# Start the service
Write-Host "Starting Wazuh service..."
Start-Service -Name "Wazuh" -ErrorAction SilentlyContinue

Write-Host "Wazuh Agent installation complete." -ForegroundColor Green
