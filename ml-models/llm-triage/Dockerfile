FROM python:3.9.18-slim
RUN groupadd -g 1000 soc && useradd -u 1000 -g soc -m -s /bin/bash socuser

WORKDIR /app
RUN chown socuser:soc /app

RUN pip install --no-cache-dir confluent-kafka requests

COPY --chown=socuser:soc triage.py .

USER socuser

ENV KAFKA_BOOTSTRAP_SERVERS=kafka:9092
ENV INPUT_TOPIC=alerts
ENV OUTPUT_TOPIC=triaged-alerts
ENV OLLAMA_URL=http://host.docker.internal:11434/api/generate
ENV OLLAMA_MODEL=llama3:latest
ENV PYTHONUNBUFFERED=1

CMD ["python", "triage.py"]
