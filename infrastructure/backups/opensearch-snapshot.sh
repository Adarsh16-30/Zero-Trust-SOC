#!/bin/bash
# OpenSearch Backup Script — Snapshot to local MinIO (S3-compatible)

set -e

REPO_NAME="minio_s3"
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
SNAPSHOT_NAME="soc-snapshot-$TIMESTAMP"

echo "[*] Registering MinIO repository in OpenSearch (if not exists)..."
# Register the MinIO endpoint as a snapshot repository
curl -X PUT "http://localhost:9200/_snapshot/$REPO_NAME" -H 'Content-Type: application/json' -d '{
  "type": "s3",
  "settings": {
    "bucket": "soc-backups",
    "endpoint": "http://minio:9000",
    "protocol": "http"
  }
}'

echo "[*] Starting OpenSearch snapshot: $SNAPSHOT_NAME..."
curl -X PUT "http://localhost:9200/_snapshot/$REPO_NAME/$SNAPSHOT_NAME?wait_for_completion=true"

echo "[+] OpenSearch Snapshot $SNAPSHOT_NAME completed."
