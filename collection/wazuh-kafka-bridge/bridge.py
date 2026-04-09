import json
import time
import os
from confluent_kafka import Producer

# Configuration
LOG_FILE = os.getenv("WAZUH_ALERT_LOG", "/var/ossec/data/logs/alerts/alerts.json")
KAFKA_BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "kafka:9092")
KAFKA_TOPIC = os.getenv("KAFKA_TOPIC", "raw-logs")

def delivery_report(err, msg):
    if err is not None:
        print(f"Message delivery failed: {err}", flush=True)
    else:
        print(f"Message delivered to {msg.topic()} [{msg.partition()}]", flush=True)

def main():
    print("Starting Wazuh-Kafka Bridge...", flush=True)

    print(f"Config - LOG_FILE: {LOG_FILE}", flush=True)
    print(f"Config - KAFKA_BOOTSTRAP_SERVERS: {KAFKA_BOOTSTRAP_SERVERS}", flush=True)
    print(f"Config - KAFKA_TOPIC: {KAFKA_TOPIC}", flush=True)
    
    # Initialize Kafka Producer
    p = Producer({'bootstrap.servers': KAFKA_BOOTSTRAP_SERVERS})

    # Wait for log file if it doesn't exist yet
    while not os.path.exists(LOG_FILE):
        print(f"Waiting for {LOG_FILE}...", flush=True)
        time.sleep(5)

    with open(LOG_FILE, 'r') as f:
        # Move to the end of the file
        f.seek(0, os.SEEK_END)
        
        while True:
            line = f.readline()
            if not line:
                time.sleep(1)
                continue
            
            try:
                # Validate JSON
                data = json.loads(line)
                
                # Send to Kafka
                p.produce(KAFKA_TOPIC, key=data.get("id"), value=json.dumps(data), callback=delivery_report)
                p.flush()
                
            except Exception as e:
                print(f"Error processing line: {e}", flush=True)

if __name__ == "__main__":
    main()
