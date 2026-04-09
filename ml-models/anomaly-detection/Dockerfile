FROM python:3.9.18-slim
RUN groupadd -g 1000 soc && useradd -u 1000 -g soc -m -s /bin/bash socuser

WORKDIR /app
RUN chown socuser:soc /app

RUN pip install --no-cache-dir confluent-kafka pandas scikit-learn numpy requests joblib

COPY --chown=socuser:soc detector.py .
COPY --chown=socuser:soc train.py .

USER socuser

ENV KAFKA_BOOTSTRAP_SERVERS=kafka:9092
ENV INPUT_TOPIC=raw-logs
ENV OUTPUT_TOPIC=alerts
ENV FORCE_RETRAIN=true
ENV PYTHONUNBUFFERED=1

CMD ["python", "detector.py"]
