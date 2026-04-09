param()

$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$projectRoot = Resolve-Path (Join-Path $scriptDir "../..")
$envFile = Join-Path $scriptDir ".env.prod"

if (-not (Test-Path $envFile)) {
    throw ".env.prod not found at $envFile"
}

$opensearchPass = (Get-Content $envFile | Where-Object { $_ -match '^OPENSEARCH_ADMIN_PASSWORD=' } | Select-Object -First 1)
if (-not $opensearchPass) {
    throw "OPENSEARCH_ADMIN_PASSWORD not found in .env.prod"
}
$opensearchPass = $opensearchPass.Split('=')[1]

Push-Location $projectRoot
try {
    # Ensure OpenSearch is running before applying security config.
    docker compose -f infrastructure/docker-compose/prod-stack.yml --env-file infrastructure/docker-compose/.env.prod up -d opensearch | Out-Null

  $ready = $false
  for ($i = 0; $i -lt 30; $i++) {
    $code = curl.exe -ks -o NUL -w "%{http_code}" https://localhost:9200/_cluster/health
    if ($code -ne "000") {
      $ready = $true
      break
    }
  }
  if (-not $ready) {
    throw "OpenSearch did not become reachable on https://localhost:9200"
  }

    # Generate bcrypt hash inside the OpenSearch container using bundled tool.
    $hash = docker exec -e NEW_PASS="$opensearchPass" opensearch-prod bash -lc 'plugins/opensearch-security/tools/hash.sh -p "$NEW_PASS"' | Select-Object -Last 1
    if (-not $hash.StartsWith('$2')) {
        throw "Failed to generate password hash for OpenSearch internal users"
    }

    $tmp = Join-Path $env:TEMP 'internal_users_p0.yml'
@"
_meta:
  type: "internalusers"
  config_version: 2

admin:
  hash: "$hash"
  reserved: true
  backend_roles:
    - "admin"
  opendistro_security_roles:
    - "all_access"
    - "security_rest_api_access"
  description: "Rotated admin user"

shuffle_svc:
  hash: "$hash"
  reserved: false
  backend_roles:
    - "admin"
  opendistro_security_roles:
    - "all_access"
  description: "Shuffle service account"
"@ | Set-Content -Path $tmp -NoNewline

    docker cp $tmp opensearch-prod:/tmp/internal_users_p0.yml | Out-Null

    docker exec opensearch-prod bash -lc 'plugins/opensearch-security/tools/securityadmin.sh -f /tmp/internal_users_p0.yml -t internalusers -icl -nhnv -cacert config/certs/ca.crt -cert config/certs/opensearch-admin.crt -key config/certs/opensearch-admin.key'

    Remove-Item $tmp -ErrorAction SilentlyContinue

    $codeStrong = curl.exe -ks -u "admin:$opensearchPass" -o NUL -w "%{http_code}" https://localhost:9200/_cluster/health
    $codeDefault = curl.exe -ks -u "admin:admin" -o NUL -w "%{http_code}" https://localhost:9200/_cluster/health

    Write-Output "admin_with_env_password_http=$codeStrong"
    Write-Output "admin_with_default_password_http=$codeDefault"
}
finally {
    Pop-Location
}
