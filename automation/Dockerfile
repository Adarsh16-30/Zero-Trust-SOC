FROM python:3.9.18-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends iptables curl \
    && rm -rf /var/lib/apt/lists/* \
    && pip install --no-cache-dir confluent-kafka requests

WORKDIR /app
COPY workflows/response_coordinator.py .
COPY response-scripts/wazuh_block.sh /usr/local/bin/wazuh_block.sh
RUN chmod +x /usr/local/bin/wazuh_block.sh

ENV KAFKA_BOOTSTRAP_SERVERS=kafka:9092
ENV INPUT_TOPIC=triaged-alerts
ENV PYTHONUNBUFFERED=1

CMD ["python", "response_coordinator.py"]
