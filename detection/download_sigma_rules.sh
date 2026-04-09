#!/bin/bash
# Downloads the official SigmaHQ community rules into the project.
# Run this once from the project root before starting the stack.

set -e

RULES_DIR="detection/sigma-rules"
UPSTREAM_DIR="$RULES_DIR/upstream"

echo "Downloading SigmaHQ community rules..."

if [ -d "$UPSTREAM_DIR" ]; then
    echo "Upstream rules already exist. Pulling latest..."
    git -C "$UPSTREAM_DIR" pull
else
    git clone --depth 1 https://github.com/SigmaHQ/sigma.git "$UPSTREAM_DIR"
fi

echo "Copying rules into project folders..."
cp -r "$UPSTREAM_DIR/rules/windows/." "$RULES_DIR/windows/" 2>/dev/null || mkdir -p "$RULES_DIR/windows" && cp -r "$UPSTREAM_DIR/rules/windows/." "$RULES_DIR/windows/"
cp -r "$UPSTREAM_DIR/rules/linux/." "$RULES_DIR/linux/"   2>/dev/null || mkdir -p "$RULES_DIR/linux"   && cp -r "$UPSTREAM_DIR/rules/linux/." "$RULES_DIR/linux/"
cp -r "$UPSTREAM_DIR/rules/cloud/." "$RULES_DIR/cloud/"   2>/dev/null || mkdir -p "$RULES_DIR/cloud"   && cp -r "$UPSTREAM_DIR/rules/cloud/." "$RULES_DIR/cloud/"
cp -r "$UPSTREAM_DIR/rules/network/." "$RULES_DIR/network/" 2>/dev/null || mkdir -p "$RULES_DIR/network" && cp -r "$UPSTREAM_DIR/rules/network/." "$RULES_DIR/network/"

RULE_COUNT=$(find "$RULES_DIR" -name "*.yml" | grep -v upstream | wc -l)
echo "Done. $RULE_COUNT rules available."

echo "Converting rules to detection engine format..."
python detection/sigma_converter.py

echo "Rules ready."
