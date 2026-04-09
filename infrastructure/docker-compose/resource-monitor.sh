#!/bin/bash
# Zero-Trust SOC — Resource Governance Monitor
# Checks container memory usage and alerts if near limit.

THRESHOLD=85
LOG_FILE="/c/Users/adars/Documents/Coding/Project/Zero-Trust/infrastructure/docker-compose/resource.log"

echo "[$(date)] Resource check started..." >> "$LOG_FILE"

# Get container stats
docker stats --no-stream --format "{{.Name}} {{.MemPerc}}" | while read -r line; do
    NAME=$(echo "$line" | cut -d' ' -f1)
    PERC=$(echo "$line" | cut -d' ' -f2 | tr -d '%')
    
    # Check if percentage exceeds threshold
    if (( $(echo "$PERC > $THRESHOLD" | bc -l) )); then
        echo "[!] WARNING: Container $NAME is at $PERC% memory usage (Limit: $THRESHOLD%)" | tee -a "$LOG_FILE"
        # Optional: Send alert to Alertmanager
    fi
done
