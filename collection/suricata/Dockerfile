FROM python:3.9.18-slim

RUN groupadd -g 1000 soc \
    && useradd -u 1000 -g soc -m -s /bin/bash socuser \
    && mkdir -p /app \
    && chown socuser:soc /app \
    && pip install --no-cache-dir confluent-kafka

WORKDIR /app
COPY --chown=socuser:soc suricata_bridge.py .
USER socuser

ENV PYTHONUNBUFFERED=1

CMD ["python", "suricata_bridge.py"]
