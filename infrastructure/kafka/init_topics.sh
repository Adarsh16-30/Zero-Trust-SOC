#!/bin/bash
# Initializes Kafka Topics

echo "Waiting for Kafka to be ready..."
# Use built-in basic sleep fallback if cub tool is missing
sleep 10

echo "Creating topics..."
kafka-topics --create --if-not-exists --bootstrap-server kafka:9092 --partitions 1 --replication-factor 1 --topic raw-logs
kafka-topics --create --if-not-exists --bootstrap-server kafka:9092 --partitions 1 --replication-factor 1 --topic enriched-events
kafka-topics --create --if-not-exists --bootstrap-server kafka:9092 --partitions 1 --replication-factor 1 --topic alerts
kafka-topics --create --if-not-exists --bootstrap-server kafka:9092 --partitions 1 --replication-factor 1 --topic triaged-alerts

echo "Topics created successfully."
