FROM python:3.9.18-slim
RUN groupadd -g 1000 soc && useradd -u 1000 -g soc -m -s /bin/bash socuser

WORKDIR /app
RUN chown socuser:soc /app

RUN pip install --no-cache-dir confluent-kafka requests

COPY --chown=socuser:soc bridge.py .

USER socuser

# Path inside the container
ENV WAZUH_ALERT_LOG=/var/ossec/logs/alerts/alerts.json
ENV KAFKA_BOOTSTRAP_SERVERS=kafka:9092
ENV KAFKA_TOPIC=raw-logs

CMD ["python", "bridge.py"]
