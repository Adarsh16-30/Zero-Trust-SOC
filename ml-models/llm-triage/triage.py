"""
Zero-Trust SOC — Hybrid Alert Triage Engine
Uses Llama 3 (via local Ollama) for intelligent alert triage,
mapping to MITRE ATT&CK, and recommending response actions.
Includes a fast rule-based fallback for when the LLM is unavailable or slow.
"""

import json
import time
import os
import re
import hashlib
import requests
from collections import defaultdict
from confluent_kafka import Consumer, Producer

KAFKA_BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "kafka:9092")
INPUT_TOPIC = os.getenv("INPUT_TOPIC", "alerts")
OUTPUT_TOPIC = os.getenv("OUTPUT_TOPIC", "triaged-alerts")
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://host.docker.internal:11434/api/generate")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3:latest")

MITRE_MAPPING = {
    "brute_force": {"tactic": "Credential Access", "technique": "T1110", "name": "Brute Force"},
    "port_scan": {"tactic": "Discovery", "technique": "T1046", "name": "Network Service Scanning"},
    "lateral_movement": {"tactic": "Lateral Movement", "technique": "T1021", "name": "Remote Services"},
    "data_exfil": {"tactic": "Exfiltration", "technique": "T1041", "name": "Exfiltration Over C2"},
    "privilege_escalation": {"tactic": "Privilege Escalation", "technique": "T1068", "name": "Exploitation for Privilege Escalation"},
    "command_control": {"tactic": "Command and Control", "technique": "T1071", "name": "Application Layer Protocol"},
    "defense_evasion": {"tactic": "Defense Evasion", "technique": "T1562", "name": "Impair Defenses"},
    "execution": {"tactic": "Execution", "technique": "T1059", "name": "Command and Scripting Interpreter"},
    "persistence": {"tactic": "Persistence", "technique": "T1053", "name": "Scheduled Task/Job"},
    "initial_access": {"tactic": "Initial Access", "technique": "T1190", "name": "Exploit Public-Facing Application"},
}

HIGH_SEVERITY_PATTERNS = [
    (r"mimikatz|credential.dump|lsass|hashdump|pass.the.hash", "credential_access"),
    (r"reverse.shell|bind.shell|meterpreter|cobalt.?strike|beacon", "command_control"),
    (r"privilege.escalat|sudo|runas|setuid|token.impersonat", "privilege_escalation"),
    (r"ransomware|encrypt|wanna.?cry|locky|crypto.?lock", "execution"),
]

LLM_SYSTEM_PROMPT = """
You are a senior SOC analyst. Analyze the following security alert and output a JSON object.
FIELDS:
- severity: (informational, low, medium, high, critical)
- mitigation: (specific technical command or action to take)
- mitre_tactic: (MITRE ATT&CK Tactic)
- mitre_technique: (MITRE ATT&CK Technique ID)
- reasoning: (one sentence explanation)

Be concise. Output JSON ONLY.
"""

class AlertHistory:
    def __init__(self, window_seconds=300, escalation_threshold=10):
        self.window = window_seconds
        self.threshold = escalation_threshold
        self.history = defaultdict(list)

    def _fingerprint(self, alert):
        rule_id = alert.get("rule_id", "unknown")
        src = alert.get("source_event", {})
        src_ip = src.get("src_ip", src.get("data", {}).get("srcip", ""))
        return hashlib.md5(f"{rule_id}:{src_ip}".encode()).hexdigest()

    def record(self, alert):
        fp = self._fingerprint(alert)
        now = time.time()
        self.history[fp] = [t for t in self.history[fp] if now - t < self.window]
        self.history[fp].append(now)
        count = len(self.history[fp])
        return count, count >= self.threshold

def rule_based_triage(alert):
    alert_text = json.dumps(alert).lower()
    severity = "low"
    category = "reconnaissance"
    reason = "No specific pattern matched"
    
    for pattern, cat in HIGH_SEVERITY_PATTERNS:
        if re.search(pattern, alert_text):
            severity = "critical"
            category = cat
            reason = f"High-threat pattern detected: {cat}"
            break
            
    mitre = MITRE_MAPPING.get(category, {"tactic": "Unknown", "technique": "N/A", "name": category})
    
    return {
        "triage_severity": severity,
        "triage_action": "BLOCK_AND_INVESTIGATE" if severity == "critical" else "INVESTIGATE",
        "triage_category": category,
        "triage_reasoning": reason + " [RULE-BASED FALLBACK]",
        "mitre_attack": mitre,
        "triage_timestamp": time.time(),
        "triage_engine": "rule-based-v2",
    }

def llm_triage(alert):
    try:
        start_time = time.time()
        prompt = f"Analyze this security alert: {json.dumps(alert)}"
        payload = {
            "model": OLLAMA_MODEL,
            "prompt": f"{LLM_SYSTEM_PROMPT}\n\n{prompt}",
            "stream": False,
            "format": "json"
        }
        
        response = requests.post(OLLAMA_URL, json=payload, timeout=10)
        response.raise_for_status()
        result = json.loads(response.json()["response"])
        
        return {
            "triage_severity": result.get("severity", "medium").lower(),
            "triage_action": "BLOCK_AND_INVESTIGATE" if result.get("severity") in ("critical", "high") else "INVESTIGATE",
            "triage_category": result.get("mitre_tactic", "Unknown"),
            "triage_reasoning": result.get("reasoning", "Analyzed by Llama 3"),
            "mitre_attack": {
                "tactic": result.get("mitre_tactic"),
                "technique": result.get("mitre_technique"),
                "name": result.get("mitre_tactic"),
            },
            "triage_timestamp": time.time(),
            "triage_engine": f"llm-{OLLAMA_MODEL}",
            "llm_time_ms": int((time.time() - start_time) * 1000)
        }
    except Exception as e:
        print(f"  [WARN] LLM Triage failed ({e}). Falling back to rules.")
        return rule_based_triage(alert)

def main():
    print(f"Starting Hybrid Triage Engine...")
    print(f"  Llama 3 @ {OLLAMA_URL}")
    print(f"  Kafka UI  : {KAFKA_BOOTSTRAP_SERVERS}")

    c = None
    p = None
    while c is None or p is None:
        try:
            c = Consumer({
                'bootstrap.servers': KAFKA_BOOTSTRAP_SERVERS,
                'group.id': 'alert-triage',
                'auto.offset.reset': 'earliest'
            })
            p = Producer({'bootstrap.servers': KAFKA_BOOTSTRAP_SERVERS})
            c.list_topics(timeout=5)
            print("✓ Connected to Kafka.")
        except Exception as e:
            print(f"⚠ Kafka not ready: {e}. Retrying...")
            time.sleep(5)

    c.subscribe([INPUT_TOPIC])
    history = AlertHistory()

    try:
        while True:
            msg = c.poll(1.0)
            if msg is None: continue
            if msg.error(): continue

            try:
                alert = json.loads(msg.value().decode('utf-8'))
            except: continue

            # Core triage logic
            triage = llm_triage(alert)
            
            # Escalation check
            count, is_escalated = history.record(alert)
            if is_escalated and triage["triage_severity"] != "critical":
                triage["triage_severity"] = "critical"
                triage["triage_reasoning"] += f" [ESCALATED: {count} events in 5min]"

            triaged_alert = {**alert, "ai_analysis": triage}
            p.produce(OUTPUT_TOPIC, value=json.dumps(triaged_alert))
            p.poll(0)

            print(f"  [{triage['triage_engine'].upper()}] Triaged {alert.get('rule_id')} -> {triage['triage_severity']}")

    except KeyboardInterrupt:
        pass
    finally:
        c.close()

if __name__ == "__main__":
    main()
