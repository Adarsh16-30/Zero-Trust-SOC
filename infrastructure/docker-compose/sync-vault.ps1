# sync-vault.ps1
# This script pulls secrets from Vault and updates the local .env file.
# It uses the Vault container to avoid requiring a local Vault binary.

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
$ProjectRoot = Resolve-Path "$ScriptDir\.."
$VaultKeysFile = "$ProjectRoot\infrastructure\vault\init_keys.json"
$EnvFile = "$ProjectRoot\infrastructure\docker-compose\.env"
$VaultContainer = "vault-prod"

if (-not (Test-Path $VaultKeysFile)) {
    Write-Error "Vault keys file not found at $VaultKeysFile. Please initialize Vault first."
    exit 1
}

$KeysJson = Get-Content $VaultKeysFile | ConvertFrom-Json
$RootToken = $KeysJson.root_token

Write-Host "Fetching secrets from Vault..." -ForegroundColor Cyan

# Fetch secrets using docker exec
$SecretsJson = docker exec -e VAULT_TOKEN=$RootToken -e VAULT_SKIP_VERIFY=true $VaultContainer vault kv get -format=json secret/zero-trust/platform | ConvertFrom-Json

if (-not $SecretsJson) {
    Write-Error "Failed to fetch secrets from Vault. Is the container running and unsealed?"
    exit 1
}

$Secrets = $SecretsJson.data.data

Write-Host "Updating $EnvFile..." -ForegroundColor Green

if (-not (Test-Path $EnvFile)) {
    New-Item $EnvFile -ItemType File
}

$EnvContent = Get-Content $EnvFile

# Map Vault keys to .env keys
$Mapping = @{
    "opensearch_admin_password" = "OPENSEARCH_ADMIN_PASSWORD"
    "keycloak_admin_password"   = "KEYCLOAK_ADMIN_PASSWORD"
    "grafana_admin_password"    = "GRAFANA_ADMIN_PASSWORD"
    "neo4j_password"            = "NEO4J_PASSWORD"
    "minio_root_password"       = "MINIO_ROOT_PASSWORD"
    "shuffle_admin_password"    = "SHUFFLE_ADMIN_PASSWORD"
    "shuffle_encryption_key"    = "SHUFFLE_ENCRYPTION_KEY"
    "smtp_password"             = "SMTP_PASSWORD"
}

foreach ($VaultKey in $Mapping.Keys) {
    $EnvKey = $Mapping[$VaultKey]
    $Value = $Secrets.$VaultKey
    
    if ($null -ne $Value) {
        if ($EnvContent -match "^$EnvKey=") {
            $EnvContent = $EnvContent -replace "^$EnvKey=.*", "$EnvKey=$Value"
        } else {
            $EnvContent += "$EnvKey=$Value"
        }
    }
}

$EnvContent | Set-Content $EnvFile
Write-Host "Sync complete. Secrets updated in $EnvFile." -ForegroundColor Green
