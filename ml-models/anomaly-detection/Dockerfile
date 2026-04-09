FROM python:3.9-slim

WORKDIR /app

RUN pip install --no-cache-dir confluent-kafka pandas scikit-learn numpy requests joblib

COPY detector.py .
COPY train.py .

ENV KAFKA_BOOTSTRAP_SERVERS=kafka:9092
ENV INPUT_TOPIC=raw-logs
ENV OUTPUT_TOPIC=alerts
ENV FORCE_RETRAIN=true

ENV PYTHONUNBUFFERED=1
CMD ["python", "detector.py"]
