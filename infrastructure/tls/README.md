# Zero-Trust SOC — Production TLS Security

This folder contains the Internal Certificate Authority (CA) and service certificates used to secure the production environment.

## 1. Initial Provisioning
To generate the root CA and individual service certificates (valid for 825 days), run the generation script from **Git Bash**:
```bash
# Run from project root
bash infrastructure/tls/generate-certs.sh
```

## 2. Directory Structure
*   `ca/`: Contains the Root CA private key (`ca.key`) and public cert (`ca.crt`). 
    *   **CRITICAL**: Keep `ca.key` secure.
*   `certs/`: Contains individual service certificates (`.crt`) and private keys (`.key`).

## 3. Trusting the Root CA
For your browser or CLI tools to trust these certificates, you must add the Root CA to your system's trust store.

### Windows (PowerShell - Admin)
```powershell
Import-Certificate -FilePath "infrastructure/tls/ca/ca.crt" -CertStoreLocation Cert:\LocalMachine\Root
```

### Linux / Docker Containers
Most containers in the `prod-stack.yml` are configured to automatically trust the CA by mounting it to `/usr/local/share/ca-certificates/` (Ubuntu/Debian) or `/etc/pki/ca-trust/source/anchors/` (Alpine/RHEL).

## 4. Service Hostnames
The certificates are issued for specific DNS names (e.g., `opensearch`, `kafka`). These only resolve correctly within the Docker network. For local access (e.g., from your browser to `https://localhost:9200`), the certificates also include `localhost` in their Subject Alternative Names (SANs).
