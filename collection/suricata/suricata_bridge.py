import json
import time
import os
from confluent_kafka import Producer

LOG_FILE = os.getenv("SURICATA_LOG_FILE", "/var/log/suricata/eve.json")
KAFKA_BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "kafka:9092")
KAFKA_TOPIC = os.getenv("KAFKA_TOPIC", "raw-logs")

def delivery_report(err, msg):
    if err is not None:
        print(f"[ERROR] Kafka delivery failed: {err}")

def main():
    print(f"Starting Suricata-Kafka Bridge. Log: {LOG_FILE}, Topic: {KAFKA_TOPIC}")
    
    # ── Connection Resilience Loop ──
    p = None
    while p is None:
        try:
            print(f"Connecting to Kafka at {KAFKA_BOOTSTRAP_SERVERS}...")
            p = Producer({"bootstrap.servers": KAFKA_BOOTSTRAP_SERVERS})
            # Quick test to see if broker is reachable
            p.list_topics(timeout=5)
            print("✓ Successfully connected to Kafka.")
        except Exception as e:
            print(f"⚠ Could not connect to Kafka: {e}. Retrying in 5s...")
            p = None
            time.sleep(5)

    while not os.path.exists(LOG_FILE):
        print(f"Waiting for {LOG_FILE}...")
        time.sleep(5)

    print(f"✓ Tailing Suricata log: {LOG_FILE}")
    with open(LOG_FILE, "r") as f:
        f.seek(0, os.SEEK_END)
        while True:
            line = f.readline()
            if not line:
                time.sleep(0.5)
                continue
            try:
                data = json.loads(line.strip())
                data["source"] = "suricata"
                p.produce(KAFKA_TOPIC, value=json.dumps(data), callback=delivery_report)
                p.poll(0)
            except json.JSONDecodeError:
                continue
            except Exception as e:
                print(f"[ERROR] Sync error: {e}")
                time.sleep(1)

if __name__ == "__main__":
    main()
