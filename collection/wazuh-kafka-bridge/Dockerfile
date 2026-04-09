FROM python:3.9-slim

WORKDIR /app

RUN pip install --no-cache-dir confluent-kafka requests

COPY bridge.py .

# Path inside the container
ENV WAZUH_ALERT_LOG=/var/ossec/logs/alerts/alerts.json
ENV KAFKA_BOOTSTRAP_SERVERS=kafka:9092
ENV KAFKA_TOPIC=raw-logs

CMD ["python", "bridge.py"]
