# PowerShell Certificate Generation for Zero-Trust SOC Production
# Uses relative filenames only to bypass Windows/Unix path conversion issues

$ErrorActionPreference = "Stop"

$OPENSSL = "C:/Program Files/Git/usr/bin/openssl.exe"
$TLS_DIR = Join-Path $PSScriptRoot "."
$CA_DIR = Join-Path $TLS_DIR "ca"
$SVC_DIR = Join-Path $TLS_DIR "certs"

if (-not (Test-Path $CA_DIR)) { New-Item -ItemType Directory -Path $CA_DIR -Force }
if (-not (Test-Path $SVC_DIR)) { New-Item -ItemType Directory -Path $SVC_DIR -Force }

Write-Host "--- Zero-Trust SOC Internal CA bootstrap ---"

# 1. Root CA
Push-Location $CA_DIR
if (-not (Test-Path "ca.key")) {
    Write-Host "[*] Generating Root CA..."
    & $OPENSSL genrsa -out "ca.key" 4096
    & $OPENSSL req -x509 -new -nodes -key "ca.key" -sha256 -days 3650 -out "ca.crt" -subj "/C=US/ST=Security/L=SOC/O=ZeroTrust/CN=ZeroTrustRootCA"
}
Pop-Location

# 2. Service Certs
function New-SvcCert {
    param($name, $dns)
    Write-Host "[*] Service: $name"
    
    Push-Location $SVC_DIR
    & $OPENSSL genrsa -out "$name.key" 2048
    $conf = "[req]`ndistinguished_name=req_dn`nreq_extensions=v3`nprompt=no`n[req_dn]`nCN=$dns`n[v3]`nkeyUsage=digitalSignature,keyEncipherment`nextendedKeyUsage=serverAuth,clientAuth`nsubjectAltName=@alt`n[alt]`nDNS.1=$dns`nDNS.2=localhost`nIP.1=127.0.0.1"
    $conf | Set-Content -Path "$name.conf" -Encoding Ascii

    & $OPENSSL req -new -key "$name.key" -out "$name.csr" -config "$name.conf"
    
    # Use relative path to CA files
    & $OPENSSL x509 -req -in "$name.csr" -CA "../ca/ca.crt" -CAkey "../ca/ca.key" -CAcreateserial -out "$name.crt" -days 825 -sha256 -extensions v3 -extfile "$name.conf"
    
    if (Test-Path "$name.csr") { Remove-Item "$name.csr" }
    if (Test-Path "$name.conf") { Remove-Item "$name.conf" }
    Pop-Location
}

New-SvcCert "opensearch" "opensearch"
New-SvcCert "kafka" "kafka"
New-SvcCert "vault" "vault"
New-SvcCert "keycloak" "keycloak"
New-SvcCert "grafana" "grafana"
New-SvcCert "minio" "minio"

Write-Host "--- TLS Provisioning Complete ---"
