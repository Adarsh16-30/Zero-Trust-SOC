#!/bin/sh
set -eu

TEMPLATE="/opt/keycloak/data/import/realm-export.template.json"
OUTPUT="/opt/keycloak/data/import/realm-export.json"

require_var() {
  var_name="$1"
  eval "var_value=\${$var_name:-}"
  if [ -z "$var_value" ]; then
    echo "Missing required environment variable: $var_name" >&2
    exit 1
  fi
}

escape_sed() {
  printf '%s' "$1" | sed -e 's/[\/&]/\\&/g'
}

require_var KEYCLOAK_GRAFANA_CLIENT_SECRET
require_var KEYCLOAK_OPENSEARCH_CLIENT_SECRET
require_var KEYCLOAK_SHUFFLE_CLIENT_SECRET
require_var SOC_ANALYST_INITIAL_PASSWORD

cp "$TEMPLATE" "$OUTPUT"

sed -i "s|__KEYCLOAK_GRAFANA_CLIENT_SECRET__|$(escape_sed "$KEYCLOAK_GRAFANA_CLIENT_SECRET")|g" "$OUTPUT"
sed -i "s|__KEYCLOAK_OPENSEARCH_CLIENT_SECRET__|$(escape_sed "$KEYCLOAK_OPENSEARCH_CLIENT_SECRET")|g" "$OUTPUT"
sed -i "s|__KEYCLOAK_SHUFFLE_CLIENT_SECRET__|$(escape_sed "$KEYCLOAK_SHUFFLE_CLIENT_SECRET")|g" "$OUTPUT"
sed -i "s|__SOC_ANALYST_INITIAL_PASSWORD__|$(escape_sed "$SOC_ANALYST_INITIAL_PASSWORD")|g" "$OUTPUT"
