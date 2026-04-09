import json
import time
import os
import subprocess
import smtplib
import ssl
import requests
from collections import defaultdict
from confluent_kafka import Consumer

# Configuration
KAFKA_BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "kafka:9092")
INPUT_TOPIC = os.getenv("INPUT_TOPIC", "triaged-alerts")
COOLDOWN_SECONDS = int(os.getenv("COOLDOWN_SECONDS", "3600"))
DRY_RUN = os.getenv("DRY_RUN", "true").lower() in ("true", "1", "yes")

# SMTP Configuration
SMTP_SERVER = os.getenv("SMTP_SERVER")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD")
ALERT_RECIPIENT = os.getenv("ALERT_RECIPIENT")

# Shuffle Configuration
SHUFFLE_WEBHOOK_URL = os.getenv("SHUFFLE_WEBHOOK_URL")

SAFE_IPS = {
    "127.0.0.1", "localhost", "0.0.0.0",
    "192.168.65.1", "172.17.0.1", "172.18.0.1",
}

INTERNAL_PREFIXES = [
    "10.", "172.16.", "172.17.", "172.18.", "172.19.", "172.20.",
    "172.21.", "172.22.", "172.23.", "172.24.", "172.25.", "172.26.",
    "172.27.", "172.28.", "172.29.", "172.30.", "172.31.",
    "192.168.", "127.", "169.254.",
]


class ResponseTracker:
    """Tracks blocked IPs with cooldown to prevent duplicate actions."""

    def __init__(self, cooldown_seconds=3600):
        self.cooldown = cooldown_seconds
        self.blocked = {}
        self.action_log = []

    def can_act(self, action_type, identifier):
        """Generic cooldown check for any action/identifier pair."""
        if identifier in SAFE_IPS:
            return False
        if any(identifier.startswith(p) for p in INTERNAL_PREFIXES):
            return False
            
        key = f"{action_type}:{identifier}"
        last_act = self.blocked.get(key, 0)
        return time.time() - last_act > self.cooldown

    def record_action(self, action_type, identifier, alert):
        key = f"{action_type}:{identifier}"
        self.blocked[key] = time.time()
        self.action_log.append({
            "timestamp": time.time(),
            "action": action_type,
            "identifier": identifier,
            "rule_id": alert.get("rule_id", "unknown"),
            "severity": alert.get("ai_analysis", {}).get("triage_severity", "unknown"),
        })

    @property
    def total_actions(self):
        return len(self.action_log)


def extract_source_ip(alert):
    """Extract source IP from various alert/event formats."""
    source_event = alert.get("source_event", {})

    # Suricata format
    ip = source_event.get("src_ip")
    if ip:
        return ip

    # Wazuh format
    data = source_event.get("data", {})
    ip = data.get("srcip") or data.get("src_ip")
    if ip:
        return ip

    # ML anomaly format
    ip = alert.get("context", {}).get("src_ip")
    if ip:
        return ip

    return None


def block_ip(ip, dry_run=True):
    """Block an IP via iptables. In dry_run mode, only logs the action."""
    if dry_run:
        print(f"  [DRY RUN] Would block IP: {ip}")
        return True
    try:
        subprocess.run(
            ["/usr/local/bin/wazuh_block.sh", "add", "root", ip],
            check=True, capture_output=True, timeout=10
        )
        print(f"  ✓ Blocked IP: {ip}")
        return True
    except Exception as e:
        print(f"  ✗ Failed to block {ip}: {e}")
        return False


def send_email_alert(alert):
    """Send an email alert via SMTP."""
    if not all([SMTP_SERVER, SMTP_USER, SMTP_PASSWORD, ALERT_RECIPIENT]):
        return False

    rule_id = alert.get("rule_id", "Unknown")
    severity = alert.get("ai_analysis", {}).get("triage_severity", "Unknown")
    
    subject = f"🚨 SOC ALERT: {rule_id} ({severity.upper()})"
    body = f"An automated response was triggered.\n\nAlert Details:\n{json.dumps(alert, indent=2)}"
    message = f"Subject: {subject}\n\n{body}"

    try:
        context = ssl.create_default_context()
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls(context=context)
            server.login(SMTP_USER, SMTP_PASSWORD)
            server.sendmail(SMTP_USER, ALERT_RECIPIENT, message)
        print(f"  📧 Email alert sent to {ALERT_RECIPIENT}")
        return True
    except Exception as e:
        print(f"  ✗ Failed to send email alert: {e}")
        return False


def dispatch_to_shuffle(alert):
    """Forward high-severity alerts to Shuffle SOAR webhook."""
    if not SHUFFLE_WEBHOOK_URL:
        return False

    try:
        response = requests.post(SHUFFLE_WEBHOOK_URL, json=alert, timeout=10)
        if response.status_code in (200, 201, 202):
            print(f"  🌀 Alert forwarded to Shuffle SOAR")
            return True
        else:
            print(f"  ✗ Shuffle returned error: {response.status_code}")
            return False
    except Exception as e:
        print(f"  ✗ Failed to dispatch to Shuffle: {e}")
        return False


def should_respond(alert):
    """Determine if an alert warrants an automated response."""
    triage = alert.get("ai_analysis", {})

    if isinstance(triage, dict):
        severity = triage.get("triage_severity", "").lower()
        action = triage.get("triage_action", "").lower()

        if action in ("block_and_investigate", "investigate_immediately"):
            return True
        if severity in ("critical", "high"):
            return True
    else:
        severity = str(alert.get("severity", "")).lower()
        if severity in ("critical", "high"):
            return True

    return False


def main():
    mode = "DRY RUN" if DRY_RUN else "LIVE"
    print(f"Starting Response Coordinator ({mode} mode)...")
    print(f"  Input    : {INPUT_TOPIC}")
    print(f"  Cooldown : {COOLDOWN_SECONDS}s")

    if DRY_RUN:
        print("  ⚠ DRY RUN enabled — no actual blocking will occur.")

    c = None
    while c is None:
        try:
            print(f"Connecting to Kafka at {KAFKA_BOOTSTRAP_SERVERS}...")
            c = Consumer({
                'bootstrap.servers': KAFKA_BOOTSTRAP_SERVERS,
                'group.id': 'response-coordinator-v5',
                'auto.offset.reset': 'earliest',
                'log.connection.close': False,
            })
            c.list_topics(timeout=5)
            print("✓ Connected to Kafka.")
        except Exception as e:
            print(f"⚠ Kafka not ready: {e}. Retrying in 5s...")
            c = None
            time.sleep(5)

    c.subscribe([INPUT_TOPIC])
    tracker = ResponseTracker(cooldown_seconds=COOLDOWN_SECONDS)

    processed = 0

    try:
        while True:
            msg = c.poll(1.0)
            if msg is None:
                continue
            if msg.error():
                continue

            try:
                alert = json.loads(msg.value().decode('utf-8'))
            except (json.JSONDecodeError, UnicodeDecodeError):
                continue

            processed += 1

            if not should_respond(alert):
                continue

            rule_id = alert.get("rule_id", "unknown")
            triage = alert.get("ai_analysis", {})
            severity = triage.get("triage_severity", alert.get("severity", ""))
            
            print(f"  🛡️ RESPONSE: {rule_id} | severity={severity.upper()}")

            # 1. IP Blocking (if IP available)
            ip = extract_source_ip(alert)
            if ip and tracker.can_act("BLOCK_IP", ip):
                if block_ip(ip, dry_run=DRY_RUN):
                    tracker.record_action("BLOCK_IP", ip, alert)

            # 2. SMTP Notification (with cooldown based on rule_id)
            if tracker.can_act("EMAIL", rule_id):
                if send_email_alert(alert):
                    tracker.record_action("EMAIL", rule_id, alert)

            # 3. Shuffle Dispatch (with cooldown based on rule_id)
            if tracker.can_act("SHUFFLE", rule_id):
                if dispatch_to_shuffle(alert):
                    tracker.record_action("SHUFFLE", rule_id, alert)

            if processed % 100 == 0:
                print(
                    f"  ── processed {processed} triaged alerts | "
                    f"actions: {tracker.total_actions}"
                )

    except KeyboardInterrupt:
        print(f"\nShutdown. Processed {processed} alerts, {tracker.total_actions} actions taken.")
    finally:
        c.close()


if __name__ == "__main__":
    main()
