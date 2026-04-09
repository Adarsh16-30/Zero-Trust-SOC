#!/bin/bash
# test-alerts.sh: Send a synthetic alert to verify delivery pipeline.

AM_HOST=${1:-localhost}
AM_PORT=${2:-9093}

echo "Testing Alertmanager delivery at http://$AM_HOST:$AM_PORT..."

curl -sf -H "Content-Type: application/json" -d '[
  {
    "labels": {
      "alertname": "SyntheticAlert_DeliveryTest",
      "severity": "critical",
      "instance": "test-host"
    },
    "annotations": {
      "summary": "Alert delivery check",
      "description": "This is a synthetic alert to test the SOC alerting pipeline."
    }
  }
]' "http://$AM_HOST:$AM_PORT/api/v2/alerts"

if [ $? -eq 0 ]; then
  echo "✅ Alert successfully accepted by Alertmanager."
  echo "You can check the Alertmanager UI at http://$AM_HOST:$AM_PORT/#/alerts"
else
  echo "❌ Failed to send alert. Is Alertmanager running?"
  exit 1
fi
