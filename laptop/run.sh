#!/bin/bash
# ==============================================================================
# run.sh — Start TARS Laptop Compute Node & Web Cockpit
# Usage: bash laptop/run.sh
# ==============================================================================

set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"

echo "=========================================================="
echo "  🚀 Booting TARS Laptop Compute Node & OLED Web Cockpit"
echo "  Working Directory: $ROOT_DIR"
echo "=========================================================="

cd "$ROOT_DIR"

# Launch FastAPI Dashboard (which also runs VisionEngine in background)
python3 -m laptop.dashboard
