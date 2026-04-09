FROM python:3.10.13-slim
RUN groupadd -g 1000 soc \
    && useradd -u 1000 -g soc -m -s /bin/bash socuser \
    && mkdir -p /app \
    && chown socuser:soc /app

WORKDIR /app

RUN pip install --no-cache-dir confluent-kafka pandas scikit-learn numpy requests joblib \
    && pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu \
    && pip install --no-cache-dir torch-geometric

COPY --chown=socuser:soc ueba_engine.py .

USER socuser

ENV KAFKA_BOOTSTRAP_SERVERS=kafka:9092
ENV INPUT_TOPIC=raw-logs
ENV OUTPUT_TOPIC=alerts
ENV BASELINE_WINDOW_HOURS=24
ENV ANOMALY_THRESHOLD=3.0
ENV NEO4J_URI=bolt://neo4j:7687
ENV NEO4J_USER=neo4j
ENV GNN_INTERVAL_SECONDS=300
ENV PYTHONUNBUFFERED=1

CMD ["python", "ueba_engine.py"]
