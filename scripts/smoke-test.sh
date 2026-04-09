#!/bin/bash
# smoke-test.sh: Verify that key platform endpoints are responsive.

echo "🔍 Starting Zero-Trust SOC Smoke Test..."

check_endpoint() {
  local service=$1
  local url=$2
  local expected_code=$3

  printf "Checking %-20s ... " "$service"
  
  # Use curl with timeout and -k (insecure for local self-signed certs)
  local code=$(curl -sk -o /dev/null -w "%{http_code}" --max-time 10 "$url")

  if [[ "$code" =~ ^($expected_code)$ ]]; then
    echo "✅ [UP] (HTTP $code)"
  else
    echo "❌ [DOWN] (HTTP $code, expected $expected_code)"
    return 1
  fi
}

# Key: Service Name | URL | Expected HTTP Code(s)
FAILED=0
check_endpoint "OpenSearch" "https://localhost:9200" "200|401" || FAILED=1
check_endpoint "Dashboards" "http://localhost:5601" "200|302" || FAILED=1
check_endpoint "Vault" "https://localhost:8200/v1/sys/health" "200|429" || FAILED=1 # 429 means uninitialized/sealed
check_endpoint "Prometheus" "http://localhost:9090/-/healthy" "200" || FAILED=1
check_endpoint "Alertmanager" "http://localhost:9093/-/healthy" "200" || FAILED=1
check_endpoint "Grafana" "https://localhost:3000/api/health" "200" || FAILED=1
check_endpoint "Keycloak" "https://localhost:8443/realms/master" "200" || FAILED=1
check_endpoint "Shuffle" "http://localhost:3001" "200" || FAILED=1

if [ $FAILED -eq 0 ]; then
  echo -e "\n🏆 ALL CRITICAL SERVICES RESPONDING!"
  exit 0
else
  echo -e "\n⚠️ SOME SERVICES ARE DOWN OR MISCONFIGURED."
  exit 1
fi
