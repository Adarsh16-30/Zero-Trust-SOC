FROM python:3.9.18-slim

RUN groupadd -g 1000 soc \
    && useradd -u 1000 -g soc -m -s /bin/bash socuser \
    && mkdir -p /app \
    && chown socuser:soc /app \
    && pip install --no-cache-dir confluent-kafka requests

WORKDIR /app
COPY --chown=socuser:soc bridge.py .
USER socuser

ENV WAZUH_ALERT_LOG=/var/ossec/logs/alerts/alerts.json
ENV KAFKA_BOOTSTRAP_SERVERS=kafka:9092
ENV KAFKA_TOPIC=raw-logs

CMD ["python", "bridge.py"]
