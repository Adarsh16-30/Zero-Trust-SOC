FROM python:3.10-slim

WORKDIR /app

RUN pip install --no-cache-dir confluent-kafka neo4j
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu
RUN pip install --no-cache-dir torch-geometric

COPY ueba_engine.py .

ENV KAFKA_BOOTSTRAP_SERVERS=kafka:9092
ENV INPUT_TOPIC=raw-logs
ENV OUTPUT_TOPIC=alerts
ENV BASELINE_WINDOW_HOURS=24
ENV ANOMALY_THRESHOLD=3.0
ENV NEO4J_URI=bolt://neo4j:7687
ENV NEO4J_USER=neo4j
ENV NEO4J_PASSWORD=changeme
ENV GNN_INTERVAL_SECONDS=300
ENV PYTHONUNBUFFERED=1

CMD ["python", "ueba_engine.py"]
