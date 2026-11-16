#!/bin/bash
# ==============================================================================
# run.sh — Start TARS Raspberry Pi Edge Node
# Usage: bash pi/run.sh
# ==============================================================================

set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"

echo "=========================================================="
echo "  🤖 Booting TARS Raspberry Pi Edge Node"
echo "  Working Directory: $ROOT_DIR"
echo "=========================================================="

cd "$ROOT_DIR"

# Pre-cleanup any stale or zombie processes from previous runs
echo "Cleaning up any stale TARS background processes..."
pkill -f "python3 -m pi\." 2>/dev/null || true
pkill -f "rpicam-vid" 2>/dev/null || true
pkill -f "arecord" 2>/dev/null || true
pkill -f "aplay" 2>/dev/null || true
sleep 0.5

# Register exit trap immediately before launching any children
PID_VIDEO=""
PID_MOTOR=""
PID_BRAIN=""

cleanup() {
    echo ""
    echo "🛑 Shutting down TARS Edge Node..."
    kill -TERM $PID_VIDEO $PID_MOTOR $PID_BRAIN 2>/dev/null || true
    sleep 0.5
    kill -9 $PID_VIDEO $PID_MOTOR $PID_BRAIN 2>/dev/null || true
    pkill -f "rpicam-vid" 2>/dev/null || true
    pkill -f "arecord" 2>/dev/null || true
    pkill -f "aplay" 2>/dev/null || true
    echo "✅ Clean shutdown complete."
    exit 0
}
trap cleanup SIGINT SIGTERM EXIT

# Ensure USB microphone hardware capture volume is at 100%
amixer -c 1 sset 'Mic' 100% >/dev/null 2>&1 || true

# Connect to Bluetooth Speaker if available
echo "Checking Bluetooth Speaker (GADPRO CYBER 100H)..."
bluetoothctl connect D0:C1:7A:D2:DE:C3 >/dev/null 2>&1 || true

# 1. Start Video Streamer (Port 5555)
echo "[1/3] Starting Video Streamer (Camera -> ZeroMQ Port 5555)..."
python3 -m pi.video_streamer >/tmp/tars_video.log 2>&1 &
PID_VIDEO=$!
echo "  ✅ Video Streamer PID: $PID_VIDEO"

# 2. Start Motor & Telemetry Serial Bridge (Port 5557/5558)
echo "[2/3] Starting Motor & Ultrasonic Bridge (ZeroMQ -> /dev/ttyUSB0)..."
python3 -m pi.motor_bridge >/tmp/tars_motor.log 2>&1 &
PID_MOTOR=$!
echo "  ✅ Motor Bridge PID: $PID_MOTOR"

sleep 0.5

# 3. Start Gemini Live Chat Brain (Audio I/O)
echo "[3/3] Starting Gemini Live Audio Brain..."
python3 -m pi.chat_brain &
PID_BRAIN=$!
echo "  ✅ Chat Brain PID: $PID_BRAIN"

echo "=========================================================="
echo "  🟢 TARS Edge Node is ONLINE. Press Ctrl+C to shut down."
echo "=========================================================="

wait $PID_VIDEO $PID_MOTOR $PID_BRAIN
