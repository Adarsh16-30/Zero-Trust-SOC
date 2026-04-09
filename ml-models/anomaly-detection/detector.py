import pandas as pd
import numpy as np
from sklearn.ensemble import IsolationForest
from sklearn.metrics import classification_report, confusion_matrix
import json
import os
import sys
import time
from confluent_kafka import Consumer, Producer
import requests
from requests.auth import HTTPBasicAuth
import urllib3
import joblib
import re
import collections

KAFKA_BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "kafka:9092")
INPUT_TOPIC = "raw-logs"
OUTPUT_TOPIC = "alerts"
FEATURE_NAMES = [
    "payload_length",
    "char_diversity",
    "digit_ratio",
    "special_char_ratio",
    "avg_word_length",
    "entropy",
]


def extract_features(payload: str) -> list:
    """Extract 6-dimensional feature vector from a log payload string."""
    length = len(payload)
    if length == 0:
        return [0.0] * len(FEATURE_NAMES)

    unique_chars = len(set(payload))
    char_diversity = unique_chars / (length + 1)
    digit_count = sum(1 for c in payload if c.isdigit())
    digit_ratio = digit_count / length
    
    # Improved word splitting for JSON (split on delimiters like : , { } [ ] " etc.)
    words = [w for w in re.split(r'[^a-zA-Z0-9]+', payload) if w]
    avg_word_length = np.mean([len(w) for w in words]) if words else 0.0

    # Robust special character count (excluding letters, digits, and spaces)
    special_count = sum(1 for c in payload if not c.isalnum() and not c.isspace())
    special_char_ratio = special_count / length

    # Shannon entropy
    freq = collections.Counter(payload)
    probs = np.array([count / length for count in freq.values()])
    entropy = -np.sum(probs * np.log2(probs + 1e-12))

    return [float(length), char_diversity, digit_ratio, special_char_ratio, avg_word_length, entropy]



def generate_synthetic_training_data(n_normal=2000, n_anomaly=40):
    """
    Generate realistic synthetic SOC log features for training.
    Normal traffic follows typical network patterns; anomalies simulate
    attack payloads (long payloads, high entropy, unusual char distributions).
    """
    rng = np.random.RandomState(42)

    print("┌─────────────────────────────────────────────────────────────┐")
    print("│  Generating Synthetic SOC Training Data                    │")
    print("├─────────────────────────────────────────────────────────────┤")
    print(f"│  Normal samples  : {n_normal:>6}                                  │")
    print(f"│  Anomaly samples : {n_anomaly:>6}  ({n_anomaly/(n_normal+n_anomaly)*100:.1f}% contamination)          │")
    print(f"│  Feature dims    : {len(FEATURE_NAMES):>6}                                  │")
    print("└─────────────────────────────────────────────────────────────┘")

    # --- Normal traffic features (very wide JSON SOC baselines) ---
    normal = np.column_stack([
        rng.normal(600, 250, size=n_normal).clip(50, 2000),       # payload_length
        rng.beta(2, 10, size=n_normal),                            # char_diversity
        rng.beta(1.5, 15, size=n_normal),                         # digit_ratio
        rng.beta(3, 8, size=n_normal),                            # special_char_ratio (widened)
        rng.normal(6.5, 3.0, size=n_normal).clip(1, 30),          # avg_word_length
        rng.normal(4.5, 1.2, size=n_normal).clip(1.5, 7.5),       # entropy (very wide)
    ])

    # --- Anomaly features (extreme outliers) ---
    anomaly = np.column_stack([
        rng.normal(3000, 1000, size=n_anomaly).clip(1500, 10000),  # extreme length
        rng.beta(8, 2, size=n_anomaly),                           # high diversity
        rng.beta(6, 2, size=n_anomaly),                           # high digits
        rng.beta(6, 1, size=n_anomaly),                           # extreme special chars
        rng.normal(40.0, 15.0, size=n_anomaly).clip(20, 150),     # very long words
        rng.normal(7.8, 0.2, size=n_anomaly).clip(7.0, 8.0),      # max entropy
    ])

    X = np.vstack([normal, anomaly])
    labels = np.array([1] * n_normal + [-1] * n_anomaly)  # 1=normal, -1=anomaly (sklearn convention)

    return X, labels



def fetch_training_features(opensearch_host, opensearch_user, opensearch_password, training_index, size=5000):
    url = f"https://{opensearch_host}/{training_index}/_search"
    query = {"size": size, "query": {"match_all": {}}}
    resp = requests.post(
        url,
        json=query,
        auth=HTTPBasicAuth(opensearch_user, opensearch_password),
        verify=False,
        timeout=20,
    )
    resp.raise_for_status()

    features = []
    hits = resp.json().get("hits", {}).get("hits", [])
    for h in hits:
        source = h.get("_source", {})
        payload = source.get("full_log", source.get("log", source.get("message", "")))
        if not payload:
            payload = json.dumps(source, separators=(",", ":"), sort_keys=True)
        if payload:
            features.append(extract_features(payload))
    return features



def train_model(X_train, y_true=None, model_path="/app/model.pkl"):
    """
    Train IsolationForest with incremental tree building and verbose output.
    """
    n_estimators_total = 300
    n_stages = 10
    trees_per_stage = n_estimators_total // n_stages
    contamination = 0.035

    print("\n" + "=" * 65)
    print("  MODEL TRAINING — IsolationForest Anomaly Detector")
    print("=" * 65)
    print(f"  Algorithm        : IsolationForest (sklearn)")
    print(f"  Total estimators : {n_estimators_total}")
    print(f"  Training stages  : {n_stages} (warm_start)")
    print(f"  Trees per stage  : {trees_per_stage}")
    print(f"  Contamination    : {contamination}")
    print(f"  Training samples : {X_train.shape[0]}")
    print(f"  Feature dims     : {X_train.shape[1]}")
    print(f"  Random state     : 42")
    print("=" * 65)

    # Print feature statistics
    print("\n┌─── Feature Statistics (Training Set) ─────────────────────────┐")
    print(f"│ {'Feature':<22} {'Mean':>8} {'Std':>8} {'Min':>8} {'Max':>8} │")
    print(f"├──────────────────────────────────────────────────────────────┤")
    for i, name in enumerate(FEATURE_NAMES):
        col = X_train[:, i]
        print(f"│ {name:<22} {col.mean():>8.2f} {col.std():>8.2f} {col.min():>8.2f} {col.max():>8.2f} │")
    print(f"└──────────────────────────────────────────────────────────────┘")

    # Incremental training with warm_start
    model = IsolationForest(
        n_estimators=trees_per_stage,
        contamination=contamination,
        max_samples="auto",
        max_features=1.0,
        bootstrap=False,
        random_state=42,
        warm_start=True,
    )

    print(f"\n  Training Progress:")
    print(f"  {'Stage':>5}  {'Trees':>6}  {'Elapsed':>10}  {'Avg Depth':>10}  {'Status'}")
    print(f"  {'─'*5}  {'─'*6}  {'─'*10}  {'─'*10}  {'─'*20}")

    t_start = time.time()
    for stage in range(1, n_stages + 1):
        model.n_estimators = trees_per_stage * stage
        t0 = time.time()
        model.fit(X_train)
        dt = time.time() - t0

        # Compute average tree depth
        avg_depth = np.mean([
            est.tree_.max_depth for est in model.estimators_[trees_per_stage * (stage - 1):]
        ])

        bar_len = 20
        filled = int(bar_len * stage / n_stages)
        bar = "█" * filled + "░" * (bar_len - filled)
        elapsed = time.time() - t_start

        print(
            f"  [{stage:>2}/{n_stages}]  {model.n_estimators:>5}   "
            f"{elapsed:>8.2f}s   {avg_depth:>8.1f}    "
            f"{bar} {stage/n_stages*100:>5.1f}%"
        )
        sys.stdout.flush()

    total_time = time.time() - t_start
    print(f"\n  ✓ Training completed in {total_time:.2f}s")


    print("\n" + "=" * 65)
    print("  MODEL EVALUATION")
    print("=" * 65)

    scores = model.decision_function(X_train)
    predictions = model.predict(X_train)

    n_normal = np.sum(predictions == 1)
    n_anomaly = np.sum(predictions == -1)

    print(f"\n  Decision Function Statistics:")
    print(f"    Mean score       : {scores.mean():>10.4f}")
    print(f"    Std score        : {scores.std():>10.4f}")
    print(f"    Min score        : {scores.min():>10.4f}")
    print(f"    Max score        : {scores.max():>10.4f}")
    print(f"    Threshold (auto) : {model.offset_:>10.4f}")

    print(f"\n  Prediction Summary (on training data):")
    print(f"    Normal  (inlier)  : {n_normal:>6}  ({n_normal/len(predictions)*100:.1f}%)")
    print(f"    Anomaly (outlier) : {n_anomaly:>6}  ({n_anomaly/len(predictions)*100:.1f}%)")

    # Score distribution histogram (text-based)
    print(f"\n  Anomaly Score Distribution:")
    hist_bins = 10
    counts, bin_edges = np.histogram(scores, bins=hist_bins)
    max_count = max(counts) if max(counts) > 0 else 1
    for i in range(hist_bins):
        bar_width = int(30 * counts[i] / max_count)
        bar = "▓" * bar_width
        label = f"  [{bin_edges[i]:>7.3f}, {bin_edges[i+1]:>7.3f})"
        print(f"    {label}  {bar} {counts[i]}")

    # If we have ground-truth labels, show classification report
    if y_true is not None:
        print(f"\n  Classification Report (Ground Truth Available):")
        print("  " + "-" * 55)
        report = classification_report(
            y_true, predictions,
            target_names=["Anomaly (-1)", "Normal  ( 1)"],
            digits=4,
        )
        for line in report.strip().split("\n"):
            print(f"    {line}")

        cm = confusion_matrix(y_true, predictions, labels=[-1, 1])
        print(f"\n  Confusion Matrix:")
        print(f"                     Predicted")
        print(f"                   Anomaly  Normal")
        print(f"    Actual Anomaly  {cm[0][0]:>5}   {cm[0][1]:>5}")
        print(f"    Actual Normal   {cm[1][0]:>5}   {cm[1][1]:>5}")

        # Compute accuracy, precision, recall
        tp = cm[0][0]
        fp = cm[1][0]
        fn = cm[0][1]
        tn = cm[1][1]
        accuracy = (tp + tn) / (tp + tn + fp + fn) if (tp + tn + fp + fn) > 0 else 0
        precision = tp / (tp + fp) if (tp + fp) > 0 else 0
        recall = tp / (tp + fn) if (tp + fn) > 0 else 0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0

        print(f"  │  F1-Score   : {f1:>8.4f}  (anomaly class)               │")
        print(f"  └─────────────────────────────────────────────────────────┘")

    # Save model
    joblib.dump(model, model_path)
    print(f"\n  ✓ Model saved to {model_path}")
    print(f"  ✓ Model size: {os.path.getsize(model_path) / 1024:.1f} KB")
    print("=" * 65 + "\n")

    return model


def main():
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

    MODEL_PATH = os.getenv("MODEL_PATH", "/app/model.pkl")
    FORCE_RETRAIN = os.getenv("FORCE_RETRAIN", "true").lower() in ("true", "1", "yes")

    # ── Phase 1: Training ────────────────────────────────────────────
    should_train = FORCE_RETRAIN or not os.path.exists(MODEL_PATH)

    if should_train:
        print("[Phase 1] Model Training")
        print("-" * 65)

        # Try to fetch real data from OpenSearch first
        opensearch_host = os.getenv("OPENSEARCH_HOST", "opensearch:9200")
        opensearch_user = os.getenv("OPENSEARCH_USER", "admin")
        opensearch_password = os.getenv("OPENSEARCH_PASSWORD")
        training_index = os.getenv("OPENSEARCH_TRAINING_INDEX", "anomaly_training_seed")

        X_train = None
        y_true = None

        if opensearch_password:
            print(f"  Attempting to fetch training data from OpenSearch...")
            print(f"  Host  : {opensearch_host}")
            print(f"  Index : {training_index}")
            try:
                features = fetch_training_features(
                    opensearch_host, opensearch_user, opensearch_password,
                    training_index, size=5000
                )
                if len(features) >= 100:
                    print(f"  ✓ Fetched {len(features)} real events from OpenSearch")
                    X_train = np.array(features)
                    y_true = None  # No ground truth labels for real data
                else:
                    print(f"  ⚠ Only {len(features)} events found (need >= 100)")
            except Exception as e:
                print(f"  ⚠ Could not reach OpenSearch: {e}")

        if X_train is None:
            print(f"\n  Falling back to synthetic SOC data generation...")
            X_train, y_true = generate_synthetic_training_data(n_normal=2000, n_anomaly=40)

        model = train_model(X_train, y_true=y_true, model_path=MODEL_PATH)
    else:
        print(f"[Phase 1] Loading pre-trained model from {MODEL_PATH}")
        model = joblib.load(MODEL_PATH)
        print(f"  ✓ Model loaded ({os.path.getsize(MODEL_PATH) / 1024:.1f} KB)\n")

    # ── Phase 2: Kafka Consumer Loop ─────────────────────────────────
    print("[Phase 2] Starting Real-Time Anomaly Detection")
    print("-" * 65)
    print(f"  Kafka broker : {KAFKA_BOOTSTRAP_SERVERS}")
    print(f"  Input topic  : {INPUT_TOPIC}")
    print(f"  Output topic : {OUTPUT_TOPIC}")
    print(f"  Consumer group: anomaly-detector")
    print()

    c = Consumer({
        'bootstrap.servers': KAFKA_BOOTSTRAP_SERVERS,
        'group.id': 'anomaly-detector',
        'auto.offset.reset': 'earliest',
        'log.connection.close': False,
    })
    p = Producer({'bootstrap.servers': KAFKA_BOOTSTRAP_SERVERS})

    c.subscribe([INPUT_TOPIC])
    print("  ✓ Subscribed to Kafka. Listening for events...\n")

    events_processed = 0
    anomalies_detected = 0
    
    # --- Calibration Phase Config ---
    CALIBRATION_SIZE = 300
    baseline_scores = []
    baseline_mean = 0.0
    baseline_std = 0.01 # small non-zero default
    calibrated = False

    try:
        while True:
            msg = c.poll(1.0)
            if msg is None:
                continue

            if msg.error():
                print(f"  [WARN] Kafka consumer error: {msg.error()}")
                continue

            try:
                raw_value = msg.value()
                if raw_value is None:
                    continue
                event = json.loads(raw_value.decode('utf-8'))
            except (UnicodeDecodeError, json.JSONDecodeError) as e:
                print(f"  [WARN] Skipping non-JSON message: {e}")
                continue

            # Extract payload and features
            payload = event.get("full_log", event.get("log", event.get("message", "")))
            if not payload:
                payload = json.dumps(event, separators=(",", ":"), sort_keys=True)
            if not payload:
                continue

            features = extract_features(payload)
            X_test = np.array([features])
            score = model.decision_function(X_test)[0]
            prediction = model.predict(X_test)[0]

            events_processed += 1
            


            if prediction == -1:
                anomalies_detected += 1
                if anomalies_detected % 50 == 0 or anomalies_detected < 10:
                    print(
                        f"  🚨 ANOMALY #{anomalies_detected} | "
                        f"score={score:.4f} | "
                        f"len={features[0]:.0f} entropy={features[5]:.2f} | "
                        f"total_events={events_processed}"
                    )
                alert = {
                    "timestamp": time.time(),
                    "type": "ML_ANOMALY",
                    "severity": "medium",
                    "anomaly_score": float(score),
                    "features": {name: float(val) for name, val in zip(FEATURE_NAMES, features)},
                    "source_event": event,
                }
                p.produce(OUTPUT_TOPIC, value=json.dumps(alert))
                p.flush()
            elif events_processed % 100 == 0:
                print(
                    f"  ── processed {events_processed} events | "
                    f"anomalies: {anomalies_detected} | "
                    f"last_score: {score:.4f}"
                )
                sys.stdout.flush()

    except KeyboardInterrupt:
        print(f"\n  Shutting down. Processed {events_processed} events, detected {anomalies_detected} anomalies.")
    finally:
        c.close()


if __name__ == "__main__":
    main()
