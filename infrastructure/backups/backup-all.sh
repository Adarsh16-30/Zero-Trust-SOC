#!/bin/bash
# Zero-Trust SOC — Master Backup Script
# Orchestrates snapshots for OpenSearch, Vault, and Grafana.

set -e

TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
BACKUP_LOG="/c/Users/adars/Documents/Coding/Project/Zero-Trust/infrastructure/backups/backup.log"

echo "[${TIMESTAMP}] Starting SOC Platform Backup..." | tee -a "$BACKUP_LOG"

# 1. OpenSearch Snapshot
if bash infrastructure/backups/opensearch-snapshot.sh; then
    echo "[${TIMESTAMP}] OpenSearch backup successful" | tee -a "$BACKUP_LOG"
else
    echo "[${TIMESTAMP}] OpenSearch backup FAILED" | tee -a "$BACKUP_LOG"
    exit 1
fi

# 2. Vault Raft Snapshot
if bash infrastructure/backups/vault-backup.sh; then
    echo "[${TIMESTAMP}] Vault backup successful" | tee -a "$BACKUP_LOG"
else
    echo "[${TIMESTAMP}] Vault backup FAILED" | tee -a "$BACKUP_LOG"
    exit 1
fi

echo "[${TIMESTAMP}] SOC Platform Backup Complete." | tee -a "$BACKUP_LOG"
