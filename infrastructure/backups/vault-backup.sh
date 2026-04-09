#!/bin/bash
# HashiCorp Vault — Raft Storage Snapshot to MinIO

set -e

TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
SNAPSHOT_FILE="/tmp/vault-snapshot-$TIMESTAMP.raft"
BUCKET_URL="http://minio:9000/soc-backups"

echo "[*] Creating Vault Raft Snapshot..."
# This requires VAULT_TOKEN to be set in environment
vault operator raft snapshot save "$SNAPSHOT_FILE"

echo "[*] Uploading snapshot to MinIO..."
# Using mc for easier MinIO interaction
mc cp "$SNAPSHOT_FILE" "local/soc-backups/vault/vault-snapshot-$TIMESTAMP.raft"

echo "[+] Vault Raft Snapshot $TIMESTAMP uploaded to MinIO."
rm "$SNAPSHOT_FILE"
