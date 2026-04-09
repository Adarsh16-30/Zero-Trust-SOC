#!/bin/bash
# Self-Signed Certificate Generation for Zero-Trust SOC Production
# Creates a Root CA and issues certificates for all internal services.

set -e

# Configuration
DAYS=3650
KEY_SIZE=4096
PROJ_ROOT=$(pwd)
CERTS_DIR="$PROJ_ROOT/infrastructure/tls"
CA_DIR="$CERTS_DIR/ca"
SVC_DIR="$CERTS_DIR/certs"

mkdir -p "$CA_DIR" "$SVC_DIR"

echo "--------------------------------------------------------"
echo "  Zero-Trust SOC — Internal CA bootstrap"
echo "--------------------------------------------------------"

# 1. Generate Root CA
if [ ! -f "$CA_DIR/ca.key" ]; then
    echo "[*] Generating Root CA Key and Certificate..."
    openssl genrsa -out "$CA_DIR/ca.key" "$KEY_SIZE"
    # MSYS_NO_PATHCONV=1 is needed to prevent Git Bash from converting the -subj string into a Windows path
    MSYS_NO_PATHCONV=1 openssl req -x509 -new -nodes -key "$CA_DIR/ca.key" -sha256 -days "$DAYS" -out "$CA_DIR/ca.crt" \
        -subj "//C=US\ST=Security\L=SOC\O=ZeroTrust\CN=ZeroTrustRootCA"
    echo "[+] Root CA Created: $CA_DIR/ca.crt"
else
    echo "[!] Root CA already exists. Skipping."
fi

# Function to generate service cert
generate_svc_cert() {
    local name=$1
    local dns=$2
    echo "[*] Generating certificate for service: $name ($dns)"
    
    # Generate Key
    openssl genrsa -out "$SVC_DIR/$name.key" 2048
    
    # Create CSR configuration
    cat > "$SVC_DIR/$name.conf" <<EOF
[req]
distinguished_name = req_distinguished_name
req_extensions = v3_req
prompt = no
[req_distinguished_name]
CN = $dns
[v3_req]
keyUsage = nonRepudiation, digitalSignature, keyEncipherment
extendedKeyUsage = serverAuth, clientAuth
subjectAltName = @alt_names
[alt_names]
DNS.1 = $dns
DNS.2 = localhost
IP.1 = 127.0.0.1
EOF

    # Generate CSR
    MSYS_NO_PATHCONV=1 openssl req -new -key "$SVC_DIR/$name.key" -out "$SVC_DIR/$name.csr" -config "$SVC_DIR/$name.conf"
    
    # Sign CSR with CA
    MSYS_NO_PATHCONV=1 openssl x509 -req -in "$SVC_DIR/$name.csr" -CA "$CA_DIR/ca.crt" -CAkey "$CA_DIR/ca.key" \
        -CAcreateserial -out "$SVC_DIR/$name.crt" -days 825 -sha256 -extensions v3_req -extfile "$SVC_DIR/$name.conf"
        
    rm "$SVC_DIR/$name.csr" "$SVC_DIR/$name.conf"
    echo "[+] Certificate Created: $SVC_DIR/$name.crt"
}

# 2. Generate Service Certificates
generate_svc_cert "opensearch" "opensearch"
generate_svc_cert "kafka" "kafka"
generate_svc_cert "vault" "vault"
generate_svc_cert "keycloak" "keycloak"
generate_svc_cert "grafana" "grafana"
generate_svc_cert "minio" "minio"

echo "--------------------------------------------------------"
echo "  TLS Provisioning Complete"
echo "--------------------------------------------------------"
