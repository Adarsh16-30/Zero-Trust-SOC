FROM python:3.9-slim

WORKDIR /app

RUN pip install --no-cache-dir confluent-kafka requests

COPY triage.py .

ENV KAFKA_BOOTSTRAP_SERVERS=kafka:9092
ENV INPUT_TOPIC=alerts
ENV OUTPUT_TOPIC=triaged-alerts
ENV OLLAMA_URL=http://host.docker.internal:11434/api/generate
ENV OLLAMA_MODEL=llama3:latest
ENV PYTHONUNBUFFERED=1

CMD ["python", "triage.py"]
