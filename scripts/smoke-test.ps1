# smoke-test.ps1
# Verify that key platform endpoints are responsive.

Write-Host "Starting Zero-Trust SOC Smoke Test..." -ForegroundColor Cyan

function Check-Endpoint {
    param (
        [string]$Service,
        [string]$Url,
        [string]$ExpectedPattern
    )

    Write-Host ("Checking {0,-20} ..." -f $Service) -NoNewline

    $Code = "000"
    try {
        $Code = (& curl.exe -k -sS -o NUL -w "%{http_code}" --max-time 10 $Url).Trim()
    } catch {
        $Code = "000"
    }

    if ($Code -eq "000" -and $Url -like "https://*") {
        try {
            [System.Net.ServicePointManager]::ServerCertificateValidationCallback = { $true }
            $resp = Invoke-WebRequest -Uri $Url -Method Get -UseBasicParsing -TimeoutSec 10
            $Code = [string][int]$resp.StatusCode
        } catch {
            if ($_.Exception.Response -and $_.Exception.Response.StatusCode) {
                $Code = [string][int]$_.Exception.Response.StatusCode
            }
        }
    }

    if ($Code -match ("^(" + $ExpectedPattern + ")$")) {
        Write-Host " [UP] (HTTP $Code)" -ForegroundColor Green
        return $true
    }

    Write-Host " [DOWN] (HTTP $Code, expected $ExpectedPattern)" -ForegroundColor Red
    return $false
}

$Failed = 0

# Key: Service Name | URL | Expected HTTP Code(s)
if (-not (Check-Endpoint "OpenSearch" "https://localhost:9200" "200|401")) { $Failed++ }
if (-not (Check-Endpoint "Dashboards" "http://localhost:5601" "200|302|503")) { $Failed++ }
if (-not (Check-Endpoint "Vault" "https://localhost:8200/v1/sys/health" "200|429|501|503")) { $Failed++ }
if (-not (Check-Endpoint "Prometheus" "http://localhost:9090/-/healthy" "200")) { $Failed++ }
if (-not (Check-Endpoint "Alertmanager" "http://localhost:9093/-/healthy" "200")) { $Failed++ }
if (-not (Check-Endpoint "Grafana" "https://localhost:3000/api/health" "200")) { $Failed++ }
if (-not (Check-Endpoint "Keycloak" "https://localhost:8443/realms/master" "200|302")) { $Failed++ }
if (-not (Check-Endpoint "Shuffle" "http://localhost:3001" "200|302")) { $Failed++ }

if ($Failed -eq 0) {
    Write-Host "`nALL CRITICAL SERVICES RESPONDING." -ForegroundColor Green
    exit 0
}

Write-Host "`n$Failed SERVICES ARE DOWN OR MISCONFIGURED." -ForegroundColor Yellow
exit 1
