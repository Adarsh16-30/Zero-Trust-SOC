FROM python:3.9-slim

WORKDIR /app

RUN pip install --no-cache-dir confluent-kafka requests

COPY detection_engine.py .

ENV KAFKA_BOOTSTRAP_SERVERS=kafka:9092
ENV INPUT_TOPIC=raw-logs
ENV OUTPUT_TOPIC=alerts

ENV PYTHONUNBUFFERED=1
CMD ["python", "detection_engine.py"]
