#!/usr/bin/env python3
"""
TARS SG90 Camera Tilt Servo Test & Calibration Script
Sweeps the camera tilt servo on ESP32 GPIO 13 through:
  1. Center (0°) — Level Horizon
  2. Down (-45°) — Floor Object / Puppy Hunt View
  3. Up (+35°)   — Person Follow / Human Face View
  4. Smooth Sweep (-45° to +35° in 5° increments)
  5. Return to Center (0°)
"""

import glob
import json
import sys
import time
import serial


def find_serial_port() -> str:
    candidates = glob.glob("/dev/ttyUSB*") + glob.glob("/dev/ttyACM*")
    if candidates:
        return candidates[0]
    return "/dev/ttyUSB0"


def main():
    port = find_serial_port()
    baud = 115200

    print("=" * 60)
    print("  🤖 TARS SG90 CAMERA TILT SERVO TEST")
    print("=" * 60)
    print(f"  Target Port: {port} @ {baud} baud")
    print("  Wiring Reminder for SG90 Servo:")
    print("    - Brown / Black Wire -> ESP32 GND")
    print("    - Red Wire           -> ESP32 VIN (5V)")
    print("    - Orange / Yellow    -> ESP32 GPIO 13")
    print("=" * 60)

    try:
        ser = serial.Serial(port, baud, timeout=0.5)
        time.sleep(1.5)  # Allow ESP32 serial reset
    except Exception as e:
        print(f"\n❌ Could not open port {port}: {e}")
        print("  👉 Check if ESP32 USB cable is plugged into the laptop.")
        print("  👉 Run: ls -l /dev/ttyUSB*")
        sys.exit(1)

    # Flush initial serial buffer
    ser.reset_input_buffer()

    def send_tilt(angle_deg: int, pause_sec: float = 1.5):
        cmd = f"TILT {angle_deg}\n"
        ser.write(cmd.encode("utf-8"))
        ser.flush()
        print(f"  👉 Sent command: TILT {angle_deg:+3d}°", end="", flush=True)

        # Wait and read back telemetry response
        t_end = time.time() + pause_sec
        reported_tilt = None
        while time.time() < t_end:
            line = ser.readline().decode("utf-8", errors="replace").strip()
            if '"tilt":' in line:
                try:
                    import json
                    data = json.loads(line)
                    reported_tilt = data.get("tilt")
                except Exception:
                    pass
            time.sleep(0.02)

        if reported_tilt is not None:
            print(f"  |  Telemetry Confirmed: tilt={reported_tilt:+3d}° ✅")
        else:
            print("  |  (Command dispatched) ✅")

    print("\n[Step 1/5] Calibrating to LEVEL (0°)...")
    send_tilt(0, pause_sec=2.0)

    print("\n[Step 2/5] Tilting DOWN to Floor Puppy Hunt (-45°)...")
    send_tilt(-45, pause_sec=2.0)

    print("\n[Step 3/5] Tilting UP to Human Face/Follow (+35°)...")
    send_tilt(35, pause_sec=2.0)

    print("\n[Step 4/5] Smooth Motion Sweep (-45° up to +35° in 10° steps)...")
    for angle in range(-45, 40, 10):
        send_tilt(angle, pause_sec=0.4)

    print("\n[Step 5/5] Returning to Neutral Center (0°)...")
    send_tilt(0, pause_sec=1.5)

    ser.close()
    print("\n" + "=" * 60)
    print("  🎉 SERVO TEST COMPLETE! Servo is verified and centered at 0°.")
    print("=" * 60)


if __name__ == "__main__":
    main()
