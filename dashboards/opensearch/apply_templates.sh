#!/bash
# Script to apply OpenSearch index templates for SOC alerts

OS_URL="https://localhost:9200"
OS_USER="admin"
OS_PASS="${OPENSEARCH_ADMIN_PASSWORD:-YourStr0ngPass123!}"

echo "Applying OpenSearch Alerts Template..."

curl -k -u "$OS_USER:$OS_PASS" -X PUT "$OS_URL/_index_template/alerts_template" -H 'Content-Type: application/json' -d'
{
  "index_patterns": ["alerts*"],
  "template": {
    "settings": {
      "number_of_shards": 1,
      "number_of_replicas": 0
    },
    "mappings": {
      "properties": {
        "timestamp": { "type": "date" },
        "rule_id": { "type": "keyword" },
        "severity": { "type": "keyword" },
        "source_event": { "type": "object" },
        "data": {
          "properties": {
            "srcip": { "type": "ip" },
            "dstip": { "type": "ip" },
            "url": { "type": "keyword" }
          }
        }
      }
    }
  }
}
'

echo -e "\nIndex template applied successfully."
