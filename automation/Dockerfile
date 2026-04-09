FROM python:3.9-slim

WORKDIR /app

# Install dependencies
RUN apt-get update && apt-get install -y iptables curl && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir confluent-kafka requests

# Copy scripts and coordinator
COPY workflows/response_coordinator.py .
COPY response-scripts/wazuh_block.sh /usr/local/bin/wazuh_block.sh
RUN chmod +x /usr/local/bin/wazuh_block.sh

# Note: We are using a simplified Kafka-driven coordinator for this phase
# to fit within the 5GB RAM limit.
ENV KAFKA_BOOTSTRAP_SERVERS=kafka:9092
ENV INPUT_TOPIC=triaged-alerts
ENV PYTHONUNBUFFERED=1

CMD ["python", "response_coordinator.py"]
