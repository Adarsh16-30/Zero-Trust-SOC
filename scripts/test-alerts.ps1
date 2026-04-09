# test-alerts.ps1
# Send a synthetic alert to verify delivery pipeline.

param (
    $AmHost = "localhost",
    $AmPort = "9093"
)

Write-Host "Testing Alertmanager delivery at http://${AmHost}:${AmPort}..." -ForegroundColor Cyan

$AlertJson = @'
[
  {
    "labels": {
      "alertname": "SyntheticAlert_DeliveryTest",
      "severity": "critical",
      "instance": "test-host"
    },
    "annotations": {
      "summary": "Alert delivery check",
      "description": "This is a synthetic alert to test the SOC alerting pipeline."
    },
    "startsAt": "2026-04-08T15:00:00Z"
  }
]
'@

try {
    $Response = Invoke-RestMethod -Uri "http://${AmHost}:${AmPort}/api/v2/alerts" -Method Post -Body $AlertJson -ContentType "application/json"
    Write-Host "Alert successfully accepted by Alertmanager." -ForegroundColor Green
    Write-Host "You can check the Alertmanager UI at http://${AmHost}:${AmPort}/#/alerts"
} catch {
    Write-Host "Failed to send alert. Is Alertmanager running?" -ForegroundColor Red
    Write-Error $_.Exception.Message
}
