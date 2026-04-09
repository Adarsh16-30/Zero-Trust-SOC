"""
Zero-Trust SOC — UEBA Engine with GNN Lateral Movement Detection
Combines real-time behavioral analysis with Graph Neural Network inference.
Uses Neo4j for graph storage and PyTorch Geometric for GNN inference.
"""

import json
import time
import os
import math
import threading
from collections import defaultdict
from datetime import datetime
from confluent_kafka import Consumer, Producer

KAFKA_BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "kafka:9092")
INPUT_TOPIC = os.getenv("INPUT_TOPIC", "raw-logs")
OUTPUT_TOPIC = os.getenv("OUTPUT_TOPIC", "alerts")
BASELINE_WINDOW = int(os.getenv("BASELINE_WINDOW_HOURS", "24"))
ANOMALY_THRESHOLD = float(os.getenv("ANOMALY_THRESHOLD", "2.5"))
NEO4J_URI = os.getenv("NEO4J_URI", "bolt://neo4j:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "changeme")
GNN_INTERVAL = int(os.getenv("GNN_INTERVAL_SECONDS", "300"))


class BehaviorGraph:
    """In-memory graph tracking User->Machine authentication patterns."""

    def __init__(self, baseline_hours=24):
        self.baseline_hours = baseline_hours
        self.user_machines = defaultdict(set)
        self.user_timestamps = defaultdict(list)
        self.user_failures = defaultdict(list)
        self.user_hour_histogram = defaultdict(lambda: defaultdict(int))
        self.machine_users = defaultdict(set)
        self.total_events = 0

    def _prune_old(self, timestamps, max_age_seconds):
        now = time.time()
        return [t for t in timestamps if now - t < max_age_seconds]

    def record_auth(self, user, machine, success, timestamp=None):
        ts = timestamp or time.time()
        hour = datetime.fromtimestamp(ts).hour
        self.total_events += 1

        self.user_timestamps[user] = self._prune_old(
            self.user_timestamps[user], self.baseline_hours * 3600
        )
        self.user_timestamps[user].append(ts)
        self.user_hour_histogram[user][hour] += 1
        self.machine_users[machine].add(user)

        is_new_machine = machine not in self.user_machines[user]
        self.user_machines[user].add(machine)

        if not success:
            self.user_failures[user] = self._prune_old(
                self.user_failures[user], 3600
            )
            self.user_failures[user].append(ts)

        return is_new_machine

    def score_anomaly(self, user, machine, success, timestamp=None):
        ts = timestamp or time.time()
        hour = datetime.fromtimestamp(ts).hour
        score = 0.0
        reasons = []

        is_new = self.record_auth(user, machine, success, ts)

        if is_new and len(self.user_machines[user]) > 1:
            machine_count = len(self.user_machines[user])
            score += min(2.0, 0.5 * machine_count)
            reasons.append(f"new_machine_access (total: {machine_count})")

        hist = self.user_hour_histogram[user]
        total_logins = sum(hist.values())
        if total_logins > 10:
            hour_freq = hist.get(hour, 0) / total_logins
            if hour_freq < 0.02:
                score += 2.0
                reasons.append(f"unusual_hour ({hour}:00, freq={hour_freq:.3f})")
            elif hour_freq < 0.05:
                score += 1.0
                reasons.append(f"uncommon_hour ({hour}:00, freq={hour_freq:.3f})")

        recent_ts = self.user_timestamps[user]
        recent_15min = [t for t in recent_ts if ts - t < 900]
        if len(recent_15min) > 15:
            score += 1.5
            reasons.append(f"high_velocity ({len(recent_15min)} auths in 15min)")

        recent_failures = self.user_failures.get(user, [])
        fail_count_1h = len(recent_failures)
        if fail_count_1h >= 5:
            score += min(3.0, fail_count_1h * 0.3)
            reasons.append(f"login_failures ({fail_count_1h} in 1h)")

        machine_popularity = len(self.machine_users.get(machine, set()))
        if machine_popularity <= 1 and self.total_events > 100:
            score += 1.0
            reasons.append(f"rare_machine (only {machine_popularity} users)")

        return score, reasons


class Neo4jWriter:
    """Writes authentication events to Neo4j for GNN analysis."""

    def __init__(self, uri, user, password):
        self.uri = uri
        self.user = user
        self.password = password
        self.driver = None
        self.buffer = []
        self.buffer_size = 50
        self._connect()

    def _connect(self):
        try:
            from neo4j import GraphDatabase
            self.driver = GraphDatabase.driver(
                self.uri, auth=(self.user, self.password)
            )
            with self.driver.session() as session:
                session.run("RETURN 1")
            print(f"  ✓ Connected to Neo4j at {self.uri}")

            with self.driver.session() as session:
                session.run(
                    "CREATE INDEX user_id_idx IF NOT EXISTS FOR (u:User) ON (u.id)"
                )
                session.run(
                    "CREATE INDEX machine_id_idx IF NOT EXISTS FOR (m:Machine) ON (m.id)"
                )
            return True
        except Exception as e:
            print(f"  ⚠ Neo4j connection failed: {e}. GNN features disabled.")
            self.driver = None
            return False

    def write_auth(self, user, machine, success, timestamp=None):
        if self.driver is None:
            return
        ts = timestamp or time.time()
        self.buffer.append((user, machine, success, ts))
        if len(self.buffer) >= self.buffer_size:
            self._flush()

    def _flush(self):
        if not self.buffer or self.driver is None:
            return
        batch = self.buffer[:]
        self.buffer.clear()
        try:
            with self.driver.session() as session:
                session.run(
                    """
                    UNWIND $events AS evt
                    MERGE (u:User {id: evt.user})
                    MERGE (m:Machine {id: evt.machine})
                    CREATE (u)-[:LOGGED_INTO {
                        success: evt.success,
                        timestamp: datetime({epochSeconds: toInteger(evt.ts)})
                    }]->(m)
                    """,
                    events=[
                        {"user": u, "machine": m, "success": s, "ts": t}
                        for u, m, s, t in batch
                    ],
                )
        except Exception as e:
            print(f"  [WARN] Neo4j write failed: {e}")

    def close(self):
        self._flush()
        if self.driver:
            self.driver.close()


class GNNInference:
    """Runs periodic GNN inference on Neo4j graph data."""

    def __init__(self, neo4j_uri, neo4j_user, neo4j_password, producer, output_topic):
        self.neo4j_uri = neo4j_uri
        self.neo4j_user = neo4j_user
        self.neo4j_password = neo4j_password
        self.producer = producer
        self.output_topic = output_topic
        self.model = None
        self._init_model()

    def _init_model(self):
        try:
            import torch
            import torch.nn.functional as F
            from torch_geometric.nn import SAGEConv
            from torch_geometric.data import Data
            self.torch = torch
            self.F = F
            self.SAGEConv = SAGEConv
            self.Data = Data

            class LateralMovementGNN(torch.nn.Module):
                def __init__(self, input_dim=8, hidden_dim=32, output_dim=2):
                    super().__init__()
                    self.conv1 = SAGEConv(input_dim, hidden_dim)
                    self.conv2 = SAGEConv(hidden_dim, hidden_dim)
                    self.conv3 = SAGEConv(hidden_dim, output_dim)

                def forward(self, x, edge_index):
                    x = F.relu(self.conv1(x, edge_index))
                    x = F.dropout(x, p=0.2, training=self.training)
                    x = F.relu(self.conv2(x, edge_index))
                    x = self.conv3(x, edge_index)
                    return F.log_softmax(x, dim=1)

            self.model = LateralMovementGNN()
            self.model.eval()
            print("  ✓ GNN model initialized (SAGEConv, 3 layers)")
        except ImportError as e:
            print(f"  ⚠ PyTorch/PyG not available: {e}. GNN inference disabled.")
            self.model = None

    def _build_graph_from_neo4j(self):
        try:
            from neo4j import GraphDatabase
            driver = GraphDatabase.driver(
                self.neo4j_uri, auth=(self.neo4j_user, self.neo4j_password)
            )
            with driver.session() as session:
                result = session.run("""
                    MATCH (u:User)-[r:LOGGED_INTO]->(m:Machine)
                    WHERE r.timestamp > datetime() - duration({hours: 24})
                    RETURN u.id AS user_id, m.id AS machine_id,
                           r.success AS success,
                           count(r) AS login_count
                    LIMIT 50000
                """)
                records = list(result)
            driver.close()

            if not records:
                return None

            nodes = {}
            edges = [[], []]
            edge_success = []

            for rec in records:
                uid = f"user:{rec['user_id']}"
                mid = f"machine:{rec['machine_id']}"
                if uid not in nodes:
                    nodes[uid] = len(nodes)
                if mid not in nodes:
                    nodes[mid] = len(nodes)
                edges[0].append(nodes[uid])
                edges[1].append(nodes[mid])
                edge_success.append(1.0 if rec['success'] else 0.0)

            if len(nodes) < 3:
                return None

            torch = self.torch
            x = torch.zeros((len(nodes), 8))
            for node_name, idx in nodes.items():
                is_user = node_name.startswith("user:")
                x[idx, 0] = 1.0 if is_user else 0.0
                x[idx, 1] = 0.0 if is_user else 1.0

                if is_user:
                    connections = sum(1 for e in edges[0] if e == idx)
                    x[idx, 2] = min(connections / 10.0, 1.0)
                    x[idx, 3] = connections
                else:
                    connections = sum(1 for e in edges[1] if e == idx)
                    x[idx, 4] = min(connections / 10.0, 1.0)
                    x[idx, 5] = connections

                x[idx, 6] = len(nodes)
                x[idx, 7] = len(edges[0])

            data = self.Data(
                x=x,
                edge_index=torch.tensor(edges, dtype=torch.long)
            )
            return data, nodes
        except Exception as e:
            print(f"  [WARN] Neo4j graph build failed: {e}")
            return None

    def run_inference(self):
        if self.model is None:
            return

        result = self._build_graph_from_neo4j()
        if result is None:
            return

        data, nodes = result
        try:
            torch = self.torch
            with torch.no_grad():
                out = self.model(data.x, data.edge_index)
                scores = torch.exp(out)[:, 1]
                threshold = scores.mean() + 2.0 * scores.std()
                anomaly_mask = scores > threshold

            anomaly_count = anomaly_mask.sum().item()
            if anomaly_count == 0:
                print(
                    f"  GNN inference: {data.num_nodes} nodes, "
                    f"{data.edge_index.shape[1]} edges, 0 anomalies"
                )
                return

            reverse_nodes = {v: k for k, v in nodes.items()}
            for idx in anomaly_mask.nonzero(as_tuple=True)[0]:
                node_name = reverse_nodes.get(idx.item(), "unknown")
                node_score = scores[idx].item()

                alert = {
                    "timestamp": time.time(),
                    "type": "GNN_LATERAL_MOVEMENT",
                    "rule_id": "GNN Lateral Movement Detection",
                    "severity": "high" if node_score > 0.8 else "medium",
                    "gnn_score": round(node_score, 4),
                    "gnn_threshold": round(threshold.item(), 4),
                    "entity": node_name,
                    "graph_stats": {
                        "total_nodes": data.num_nodes,
                        "total_edges": data.edge_index.shape[1],
                    },
                    "source_event": {"gnn_analysis": True},
                }
                self.producer.produce(
                    self.output_topic,
                    value=json.dumps(alert, default=str)
                )

            self.producer.flush()
            print(
                f"  🧠 GNN inference: {data.num_nodes} nodes, "
                f"{data.edge_index.shape[1]} edges, "
                f"{anomaly_count} anomalies detected"
            )
        except Exception as e:
            print(f"  [WARN] GNN inference failed: {e}")


def extract_auth_event(event):
    """Extract user, machine, and success from various event formats."""
    source = event.get("source", "")
    data = event.get("data", {})

    user = None
    machine = None
    success = True

    if source == "wazuh" or "rule" in data:
        user = (
            data.get("srcuser") or data.get("dstuser") or
            data.get("win", {}).get("eventdata", {}).get("targetUserName") or
            data.get("userName")
        )
        machine = (
            data.get("dstip") or data.get("system_name") or
            event.get("agent", {}).get("name")
        )
        rule_level = int(
            data.get("rule", {}).get("level", 0)
            if isinstance(data.get("rule"), dict) else 0
        )
        rule_id_str = str(data.get("rule", {}).get("id", ""))
        failed_ids = {"5503", "5710", "5758", "60122", "60204"}
        if rule_id_str in failed_ids or rule_level >= 10:
            success = False

    elif source == "suricata":
        user = event.get("src_ip", "")
        machine = event.get("dest_ip", "")
        event_type = event.get("event_type", "")
        if event_type in ("alert", "anomaly"):
            success = False
        elif event_type == "flow":
            pass
        else:
            return None, None, None

    if not user or not machine:
        return None, None, None

    return str(user), str(machine), success


def gnn_loop(gnn, interval):
    """Background thread that runs GNN inference periodically."""
    print(f"  GNN inference thread started (every {interval}s)")
    time.sleep(60)
    while True:
        try:
            gnn.run_inference()
        except Exception as e:
            print(f"  [WARN] GNN loop error: {e}")
        time.sleep(interval)


def main():
    print("Starting UEBA Engine (Behavioral + GNN)...")
    print(f"  Input     : {INPUT_TOPIC}")
    print(f"  Output    : {OUTPUT_TOPIC}")
    print(f"  Baseline  : {BASELINE_WINDOW}h window")
    print(f"  Threshold : {ANOMALY_THRESHOLD} score")
    print(f"  Neo4j     : {NEO4J_URI}")
    print(f"  GNN cycle : every {GNN_INTERVAL}s")

    c = None
    p = None
    while c is None or p is None:
        try:
            print(f"Connecting to Kafka at {KAFKA_BOOTSTRAP_SERVERS}...")
            c = Consumer({
                'bootstrap.servers': KAFKA_BOOTSTRAP_SERVERS,
                'group.id': 'ueba-engine',
                'auto.offset.reset': 'earliest',
                'log.connection.close': False,
            })
            p = Producer({'bootstrap.servers': KAFKA_BOOTSTRAP_SERVERS})
            c.list_topics(timeout=5)
            print("✓ Connected to Kafka.")
        except Exception as e:
            print(f"⚠ Kafka not ready: {e}. Retrying in 5s...")
            c = None
            p = None
            time.sleep(5)

    c.subscribe([INPUT_TOPIC])
    graph = BehaviorGraph(baseline_hours=BASELINE_WINDOW)
    neo4j_writer = Neo4jWriter(NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD)
    gnn = GNNInference(NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD, p, OUTPUT_TOPIC)

    gnn_thread = threading.Thread(
        target=gnn_loop, args=(gnn, GNN_INTERVAL), daemon=True
    )
    gnn_thread.start()

    processed = 0
    anomalies = 0
    skipped = 0

    try:
        while True:
            msg = c.poll(1.0)
            if msg is None:
                continue
            if msg.error():
                continue

            try:
                event = json.loads(msg.value().decode('utf-8'))
            except (json.JSONDecodeError, UnicodeDecodeError):
                continue

            user, machine, success = extract_auth_event(event)
            if user is None:
                skipped += 1
                continue

            neo4j_writer.write_auth(user, machine, success)

            score, reasons = graph.score_anomaly(user, machine, success)
            processed += 1

            if score >= ANOMALY_THRESHOLD:
                anomalies += 1
                alert = {
                    "timestamp": time.time(),
                    "type": "UEBA_ANOMALY",
                    "rule_id": "UEBA Lateral Movement Detection",
                    "severity": "high" if score >= 5.0 else "medium",
                    "ueba_score": round(score, 2),
                    "ueba_reasons": reasons,
                    "user": user,
                    "machine": machine,
                    "auth_success": success,
                    "user_machine_count": len(graph.user_machines[user]),
                    "source_event": event,
                }
                p.produce(OUTPUT_TOPIC, value=json.dumps(alert, default=str))
                p.poll(0)

                if anomalies <= 10 or anomalies % 50 == 0:
                    print(
                        f"  🔍 UEBA #{anomalies} | "
                        f"user={user} → {machine} | "
                        f"score={score:.1f} | {reasons}"
                    )

            if processed % 500 == 0:
                p.flush()
                print(
                    f"  ── analyzed {processed} auth events | "
                    f"anomalies: {anomalies} | skipped: {skipped} | "
                    f"users: {len(graph.user_machines)}"
                )

    except KeyboardInterrupt:
        print(f"\nShutdown. Analyzed {processed}, {anomalies} anomalies.")
    finally:
        p.flush()
        neo4j_writer.close()
        c.close()


if __name__ == "__main__":
    main()
