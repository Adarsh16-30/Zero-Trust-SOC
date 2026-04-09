#!/bin/bash
# Compliance audit entrypoint.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "Starting SOC Platform Compliance Audit..."
python "$SCRIPT_DIR/audit_check.py"
