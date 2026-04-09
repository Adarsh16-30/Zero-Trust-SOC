FROM python:3.9-slim
ENV PYTHONUNBUFFERED=1
WORKDIR /app
RUN pip install --no-cache-dir confluent-kafka
COPY suricata_bridge.py .
CMD ["python", "suricata_bridge.py"]
