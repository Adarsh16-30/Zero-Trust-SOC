# Zero-Trust SOC — Disaster Recovery & Restore Runbook

This guide contains step-by-step instructions for restoring service data from MinIO snapshots.

## 1. OpenSearch Restore

To restore the `soc-snapshots` repository from MinIO:

1.  **List existing snapshots**:
    ```bash
    curl -X GET "http://localhost:9200/_snapshot/minio_s3/_all?pretty"
    ```
2.  **Restore a specific snapshot**:
    ```bash
    # Replace <SNAPSHOT_NAME> with the timestamp from the list above
    curl -X POST "http://localhost:9200/_snapshot/minio_s3/<SNAPSHOT_NAME>/_restore?wait_for_completion=true"
    ```

## 2. Vault Raft Restore

To restore the Vault Raft database from a snapshot file in MinIO:

1.  **Download the snapshot from MinIO**:
    ```bash
    mc cp "local/soc-backups/vault/vault-snapshot-YYYYMMDD_HHMMSS.raft" /tmp/vault-restore.raft
    ```
2.  **Perform the restore**:
    ```bash
    vault operator raft snapshot restore /tmp/vault-restore.raft
    ```
    *Note: The cluster will transition to the state from the snapshot and restart.*

## 3. Keycloak & Grafana
These services are git-versioned. To restore them:
1.  **Keycloak**: Re-import `identity/keycloak/realm-export.json` via UI or CLI.
2.  **Grafana**: Re-import dashboards from `dashboards/grafana/dashboards/*.json`.
