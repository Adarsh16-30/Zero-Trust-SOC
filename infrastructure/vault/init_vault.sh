#!/bin/bash
# Script to initialize, unseal and seed Hashicorp Vault in the Docker stack.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
KEYS_FILE="$SCRIPT_DIR/init_keys.json"
ENV_FILE="$PROJECT_ROOT/infrastructure/docker-compose/.env"
VAULT_CONTAINER="vault-prod"

if ! command -v docker >/dev/null 2>&1; then
    echo "[ERROR] docker command not found."
    exit 1
fi

if ! docker info >/dev/null 2>&1; then
    echo "[ERROR] Docker daemon is not reachable. Start Docker Desktop and retry."
    exit 1
fi

if ! docker ps --format '{{.Names}}' | grep -q "^${VAULT_CONTAINER}$"; then
    echo "[ERROR] Vault container '${VAULT_CONTAINER}' is not running. Start the stack first."
    exit 1
fi

wait_for_vault() {
    echo "Waiting for Vault API..."
    for _ in $(seq 1 60); do
        state="$(docker inspect -f '{{.State.Status}}' "$VAULT_CONTAINER" 2>/dev/null || echo "unknown")"
        if [ "$state" = "exited" ] || [ "$state" = "dead" ]; then
            echo "[ERROR] Vault container is '$state'. Showing recent logs:"
            docker logs --tail 80 "$VAULT_CONTAINER" || true
            exit 1
        fi
        # `vault status` exit codes are meaningful:
        # 0=unsealed, 1=error, 2=sealed/uninitialized. Treat 0 and 2 as reachable.
        if docker exec -e VAULT_SKIP_VERIFY=true "$VAULT_CONTAINER" sh -c "vault status >/dev/null 2>&1; code=\$?; [ \"\$code\" -eq 0 ] || [ \"\$code\" -eq 2 ]"; then
            return 0
        fi
        sleep 2
    done
    echo "[ERROR] Vault did not become ready in time. Current state: $(docker inspect -f '{{.State.Status}}' "$VAULT_CONTAINER" 2>/dev/null || echo unknown)"
    echo "Recent Vault logs:"
    docker logs --tail 80 "$VAULT_CONTAINER" || true
    exit 1
}

get_json_field() {
    local file="$1"
    local expr="$2"
    python - "$file" "$expr" <<'PY'
import json, sys
path = sys.argv[1]
expr = sys.argv[2]
with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
if expr == "unseal_key_0":
        print(data["unseal_keys_b64"][0])
elif expr == "root_token":
        print(data["root_token"])
else:
        raise SystemExit("unsupported expr")
PY
}

is_vault_sealed() {
    local status_json
    status_json="$(docker exec -e VAULT_SKIP_VERIFY=true "$VAULT_CONTAINER" sh -c "vault status -format=json 2>/dev/null || true")"

    if echo "$status_json" | grep -q '"sealed"[[:space:]]*:[[:space:]]*true'; then
        return 0
    fi
    return 1
}

unseal_vault() {
    local keys_file="$1"
    python - "$keys_file" <<'PY' | while IFS= read -r key; do
import json, sys
with open(sys.argv[1], "r", encoding="utf-8") as f:
    data = json.load(f)
for k in data.get("unseal_keys_b64", []):
    print(k)
PY
        if ! is_vault_sealed; then
            break
        fi
        docker exec -e VAULT_SKIP_VERIFY=true "$VAULT_CONTAINER" vault operator unseal "$key" >/dev/null
    done
}

load_env_value() {
    local key="$1"
    if [ -f "$ENV_FILE" ]; then
        grep -E "^${key}=" "$ENV_FILE" | tail -n 1 | cut -d'=' -f2- || true
    fi
}

seed_vault() {
    local root_token="$1"
    local opensearch_pass="$(load_env_value OPENSEARCH_ADMIN_PASSWORD)"
    local keycloak_pass="$(load_env_value KEYCLOAK_ADMIN_PASSWORD)"
    local grafana_pass="$(load_env_value GRAFANA_ADMIN_PASSWORD)"
    local neo4j_pass="$(load_env_value NEO4J_PASSWORD)"
    local minio_pass="$(load_env_value MINIO_ROOT_PASSWORD)"
    local shuffle_pass="$(load_env_value SHUFFLE_ADMIN_PASSWORD)"
    local shuffle_key="$(load_env_value SHUFFLE_ENCRYPTION_KEY)"
    local smtp_pass="$(load_env_value SMTP_PASSWORD)"

    echo "Seeding Vault secrets (idempotent upsert)..."
    docker exec -e VAULT_SKIP_VERIFY=true -e VAULT_TOKEN="$root_token" "$VAULT_CONTAINER" sh -c "vault secrets enable -path=secret kv-v2 >/dev/null 2>&1 || true"

    docker exec -e VAULT_SKIP_VERIFY=true -e VAULT_TOKEN="$root_token" "$VAULT_CONTAINER" sh -c \
        "vault kv put secret/zero-trust/platform \
            opensearch_admin_password='${opensearch_pass}' \
            keycloak_admin_password='${keycloak_pass}' \
            grafana_admin_password='${grafana_pass}' \
            neo4j_password='${neo4j_pass}' \
            minio_root_password='${minio_pass}' \
            shuffle_admin_password='${shuffle_pass}' \
            shuffle_encryption_key='${shuffle_key}' \
            smtp_password='${smtp_pass}' >/dev/null"

    echo "Vault secret written at secret/zero-trust/platform"
}


wait_for_vault

VAULT_INITIALIZED="false"
VAULT_STATUS_JSON="$(docker exec -e VAULT_SKIP_VERIFY=true "$VAULT_CONTAINER" sh -c "vault status -format=json 2>/dev/null || true")"

if echo "$VAULT_STATUS_JSON" | grep -q '"initialized"[[:space:]]*:[[:space:]]*true'; then
    VAULT_INITIALIZED="true"
elif echo "$VAULT_STATUS_JSON" | grep -q '"initialized"[[:space:]]*:[[:space:]]*false'; then
    VAULT_INITIALIZED="false"
else
    echo "[ERROR] Unable to determine Vault initialization state."
    docker logs --tail 80 "$VAULT_CONTAINER" || true
    exit 1
fi

if [ "$VAULT_INITIALIZED" = "false" ]; then
    echo "Initializing Vault..."
    INIT_RESPONSE="$(docker exec -e VAULT_SKIP_VERIFY=true "$VAULT_CONTAINER" vault operator init -format=json)"

    if [ -f "$KEYS_FILE" ]; then
        mv "$KEYS_FILE" "${KEYS_FILE}.bak.$(date +%Y%m%d%H%M%S)"
        echo "Existing key file backed up before writing new initialization keys."
    fi

    echo "$INIT_RESPONSE" > "$KEYS_FILE"
    chmod 600 "$KEYS_FILE"
    echo "Initial keys saved to $KEYS_FILE (SECURE THIS FILE)"
else
    if [ ! -f "$KEYS_FILE" ]; then
        LATEST_KEYS_BACKUP="$(ls -1t "$SCRIPT_DIR"/init_keys.json.bak.* 2>/dev/null | head -n 1 || true)"
        if [ -n "$LATEST_KEYS_BACKUP" ] && [ -f "$LATEST_KEYS_BACKUP" ]; then
            cp "$LATEST_KEYS_BACKUP" "$KEYS_FILE"
            chmod 600 "$KEYS_FILE"
            echo "Restored missing init key file from backup: $LATEST_KEYS_BACKUP"
        else
            echo "[ERROR] Vault is already initialized but $KEYS_FILE is missing. Cannot unseal automatically."
            echo "No backup key files were found at $SCRIPT_DIR/init_keys.json.bak.*"
            echo "Use your existing unseal keys manually, or restore the key file."
            exit 1
        fi
    fi
    echo "Using existing key material in $KEYS_FILE"
fi

ROOT_TOKEN="$(get_json_field "$KEYS_FILE" root_token)"

if docker exec -e VAULT_SKIP_VERIFY=true "$VAULT_CONTAINER" sh -c "vault status | grep -q 'Sealed.*true'"; then
    echo "Unsealing Vault..."
    unseal_vault "$KEYS_FILE"
    if is_vault_sealed; then
        echo "[ERROR] Vault is still sealed after applying available unseal keys."
        exit 1
    fi
else
    echo "Vault is already unsealed."
fi

seed_vault "$ROOT_TOKEN"
echo "Vault is ready."
