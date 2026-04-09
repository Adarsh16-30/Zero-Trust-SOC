import json
import time
import os
from confluent_kafka import Consumer, Producer

# Configuration
KAFKA_BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "kafka:9092")
INPUT_TOPIC = "raw-logs"
OUTPUT_TOPIC = "alerts"
RULES_FILE = "/app/config/active_rules.json"

def main():
    print("Starting Detection Engine...")
    
    # ── Connection Resilience Loop ──
    c = None
    p = None
    while c is None or p is None:
        try:
            print(f"Connecting to Kafka at {KAFKA_BOOTSTRAP_SERVERS}...")
            c = Consumer({
                'bootstrap.servers': KAFKA_BOOTSTRAP_SERVERS,
                'group.id': 'detection-engine',
                'auto.offset.reset': 'earliest'
            })
            p = Producer({'bootstrap.servers': KAFKA_BOOTSTRAP_SERVERS})
            # Test connection
            c.list_topics(timeout=5)
            print("✓ Successfully connected to Kafka.")
        except Exception as e:
            print(f"⚠ Could not connect to Kafka: {e}. Retrying in 5s...")
            c = None
            p = None
            time.sleep(5)
    
    c.subscribe([INPUT_TOPIC])

    # Load Rules
    with open(RULES_FILE, 'r') as f:
        rules = json.load(f)
    print(f"Loaded {len(rules)} detection rules.")

    try:
        while True:
            msg = c.poll(1.0)
            if msg is None:
                continue
            if msg.error():
                print(f"Consumer error: {msg.error()}")
                continue

            event = json.loads(msg.value().decode('utf-8'))
            
            # Simple Rule Matching Logic
            for rule in rules:
                match = True
                conditions = rule.get("conditions") or {}
                
                if not isinstance(conditions, dict):
                    match = False
                    continue

                # Check each condition field
                # Supports: field (eq), field|contains, field|exclude, field|startswith
                data_block = event.get("data", {})
                if not data_block and "source" in event:
                    # Fallback for events with top-level fields
                    data_block = event

                for field, values in conditions.items():
                    parts = field.split("|")
                    clean_field = parts[0]
                    operator = parts[1] if len(parts) > 1 else "eq"
                    
                    # Resolve nested fields (e.g., 'http.user_agent')
                    target_value = data_block
                    field_found = True
                    for key in clean_field.split("."):
                        if isinstance(target_value, dict) and key in target_value:
                            target_value = target_value.get(key)
                        else:
                            field_found = False
                            break

                    if not field_found:
                        # Skip this rule if the required field is missing from the event
                        match = False
                        break

                    target_str = str(target_value)
                    val_list = values if isinstance(values, list) else [values]
                    
                    if operator == "contains":
                        if not any(str(v) in target_str for v in val_list):
                            match = False
                    elif operator == "exclude" or operator == "not":
                        if any(str(v) in target_str for v in val_list):
                            match = False
                    elif operator == "startswith":
                        if not any(target_str.startswith(str(v)) for v in val_list):
                            match = False
                    else: # eq
                        if not any(str(v) == target_str for v in val_list):
                            match = False
                    
                    if not match:
                        break

                
                if match:
                    alert = {
                        "timestamp": time.time(),
                        "rule_id": rule.get("id"),
                        "severity": rule.get("level"),
                        "source_event": event
                    }
                    print(f"ALERT DETECTED: {rule.get('id')}")
                    p.produce(OUTPUT_TOPIC, value=json.dumps(alert))
                    p.flush()

    except KeyboardInterrupt:
        pass
    finally:
        c.close()

if __name__ == "__main__":
    main()
