#!/usr/bin/env python3
"""Run baseline compliance checks and emit OpenRMF-ready evidence."""

import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPORT_DIR = ROOT / "compliance" / "reports"
REPORT_DIR.mkdir(parents=True, exist_ok=True)
ENV_FILE = ROOT / "infrastructure" / "docker-compose" / ".env"


def run_cmd(args):
    try:
        proc = subprocess.run(args, capture_output=True, text=True, timeout=20)
        return proc.returncode, (proc.stdout or "").strip(), (proc.stderr or "").strip()
    except Exception as exc:
        return 1, "", str(exc)


def load_dotenv_value(key):
    if not ENV_FILE.exists():
        return None

    for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        if k.strip() == key:
            return v.strip()
    return None


def check_docker_running():
    code, out, err = run_cmd(["docker", "ps", "--format", "{{.Names}}"])
    passed = code == 0
    return {
        "control_id": "ZT-CIS-01",
        "title": "Docker control plane reachable",
        "status": "pass" if passed else "fail",
        "details": out if passed else err or "docker command failed",
    }


def check_vault_health():
    code, out, err = run_cmd(["curl", "-ks", "https://localhost:8200/v1/sys/health"])
    passed = code == 0 and '"initialized":true' in out
    return {
        "control_id": "ZT-CIS-02",
        "title": "Vault initialized",
        "status": "pass" if passed else "fail",
        "details": out if passed else err or out or "vault health probe failed",
    }


def check_opensearch_health():
    user = os.getenv("OPENSEARCH_USER", "admin")
    candidates = [
        ("env.OPENSEARCH_ADMIN_PASSWORD", os.getenv("OPENSEARCH_ADMIN_PASSWORD")),
        ("env.OPENSEARCH_INITIAL_ADMIN_PASSWORD", os.getenv("OPENSEARCH_INITIAL_ADMIN_PASSWORD")),
        ("dotenv.OPENSEARCH_ADMIN_PASSWORD", load_dotenv_value("OPENSEARCH_ADMIN_PASSWORD")),
        ("dotenv.OPENSEARCH_INITIAL_ADMIN_PASSWORD", load_dotenv_value("OPENSEARCH_INITIAL_ADMIN_PASSWORD")),
        ("fallback.admin", "admin"),
    ]

    seen = set()
    attempted = []
    passed = False
    details = "opensearch health probe failed"

    for source, password in candidates:
        if not password:
            continue
        if password in seen:
            continue
        seen.add(password)

        code, out, err = run_cmd(
            [
                "curl",
                "-ks",
                "-u",
                f"{user}:{password}",
                "https://localhost:9200/_cluster/health",
            ]
        )
        attempted.append(source)
        if code == 0 and '"status"' in out:
            passed = True
            details = f"auth_source={source}; {out}"
            break

        if err:
            details = err

    if not passed:
        details = f"{details}; attempted={','.join(attempted) if attempted else 'none'}"

    return {
        "control_id": "ZT-CIS-03",
        "title": "OpenSearch cluster health readable",
        "status": "pass" if passed else "fail",
        "details": details,
    }


def build_openrmf_ready(results):
    findings = []
    for item in results:
        findings.append(
            {
                "framework": "CIS",
                "control": item["control_id"],
                "title": item["title"],
                "result": item["status"],
                "evidence": item["details"],
            }
        )

    return {
        "schema": "openrmf-ready-assessment/v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "findings": findings,
    }


def main():
    checks = [check_docker_running(), check_vault_health(), check_opensearch_health()]
    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total": len(checks),
        "pass": sum(1 for c in checks if c["status"] == "pass"),
        "fail": sum(1 for c in checks if c["status"] == "fail"),
        "checks": checks,
    }

    audit_file = REPORT_DIR / "compliance_audit.json"
    openrmf_file = REPORT_DIR / "openrmf_ready_assessment.json"

    audit_file.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    openrmf_file.write_text(json.dumps(build_openrmf_ready(checks), indent=2), encoding="utf-8")

    print(f"Compliance audit report: {audit_file}")
    print(f"OpenRMF-ready report: {openrmf_file}")
    print(f"Checks passed: {summary['pass']}/{summary['total']}")

    return 0 if summary["fail"] == 0 else 2


if __name__ == "__main__":
    sys.exit(main())
