#!/bin/bash
# Zero-Trust SOC — Production Password Generator
# Generates strong random passwords for all services.

set -e

PROD_ENV="infrastructure/docker-compose/.env.prod"

generate_pass() {
    openssl rand -base64 24 | tr -d '/+=' | cut -c1-20
}

echo "[*] Generating production secrets in $PROD_ENV..."

cat > "$PROD_ENV" <<EOF
# Project Configuration (Production)
COMPOSE_PROJECT_NAME=zero-trust-soc-prod

# OpenSearch
OPENSEARCH_ADMIN_PASSWORD=$(generate_pass)
OPENSEARCH_INITIAL_ADMIN_PASSWORD=\${OPENSEARCH_ADMIN_PASSWORD}

# MinIO
MINIO_ROOT_PASSWORD=$(generate_pass)

# Grafana
GRAFANA_ADMIN_PASSWORD=$(generate_pass)

# Keycloak
KEYCLOAK_ADMIN_PASSWORD=$(generate_pass)
KC_ADMIN_PASSWORD=\${KEYCLOAK_ADMIN_PASSWORD}

# Vault
VAULT_ROOT_TOKEN=$(generate_pass)

# SMTP (Gmail)
SMTP_USER="YOUR_GMAIL_USERNAME"
SMTP_APP_PASSWORD="YOUR_GMAIL_APP_PASSWORD"

# Encryption Keys
SHUFFLE_ENCRYPTION_KEY=$(openssl rand -hex 32)
EOF

chmod 600 "$PROD_ENV"
echo "[+] Done. PLEASE UPDATE SMTP_USER AND SMTP_APP_PASSWORD IN $PROD_ENV MANUALLY."
