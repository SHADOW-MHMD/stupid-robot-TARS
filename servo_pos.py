#!/usr/bin/env python3
"""
Interactive TARS Servo Angle Positioner
Sets the camera tilt servo to exact angles:
  0     -> Level Horizon (Neutral 0°)
  max   -> Maximum Tilt Up (+45°)
  min   -> Maximum Tilt Down (-45°)
  <num> -> Any specific angle between -45° and +45°
"""

import glob
import sys
import time
import serial


def get_port():
    ports = glob.glob("/dev/ttyUSB*") + glob.glob("/dev/ttyACM*")
    return ports[0] if ports else "/dev/ttyUSB0"


def send_tilt(ser, angle: int):
    # Flush any stale incoming data first
    ser.reset_input_buffer()
    cmd = f"TILT {angle}\n"
    ser.write(cmd.encode("utf-8"))
    ser.flush()
    print(f"👉 Sent: TILT {angle:+3d}°", end="", flush=True)

    t_end = time.time() + 1.0
    confirmed = False
    while time.time() < t_end:
        line = ser.readline().decode("utf-8", errors="replace").strip()
        if '"tilt":' in line:
            print(f"  |  Confirmed: {line} ✅")
            confirmed = True
            break
        time.sleep(0.02)
    if not confirmed:
        print("  |  (Command Sent) ✅")


def open_serial(port: str):
    s = serial.Serial()
    s.port = port
    s.baudrate = 115200
    s.timeout = 0.5
    s.dtr = False
    s.rts = False
    s.open()
    # Wait for serial line stabilization
    time.sleep(1.8)
    s.reset_input_buffer()
    return s


def main():
    port = get_port()
    try:
        ser = open_serial(port)
    except Exception as e:
        print(f"\n❌ Could not open {port}: {e}")
        print("👉 Run this in your terminal: sudo chmod 666 /dev/ttyUSB0")
        sys.exit(1)

    if len(sys.argv) > 1:
        arg = sys.argv[1].lower()
        if arg in ("0", "zero", "center"):
            send_tilt(ser, 0)
        elif arg in ("max", "up"):
            send_tilt(ser, 45)
        elif arg in ("min", "down"):
            send_tilt(ser, -45)
        else:
            try:
                val = int(arg)
                send_tilt(ser, val)
            except ValueError:
                print(f"Unknown angle: {arg}")
        ser.close()
        return

    print("=" * 55)
    print("  🤖 TARS Camera Tilt Angle Controller")
    print("=" * 55)
    print("  Type any angle or shortcut:")
    print("    0    -> Center / Level Horizon (0°)")
    print("    max  -> Max Tilt Up (+45°)")
    print("    min  -> Max Tilt Down (-45°)")
    print("    <N>  -> Any angle (e.g. 15, -30, 40)")
    print("    q    -> Exit")
    print("=" * 55)

    while True:
        try:
            val_str = input("\nEnter angle (0 / max / min / num): ").strip().lower()
            if val_str in ("q", "quit", "exit"):
                break
            if val_str in ("0", "zero", "center"):
                send_tilt(ser, 0)
            elif val_str in ("max", "up"):
                send_tilt(ser, 45)
            elif val_str in ("min", "down"):
                send_tilt(ser, -45)
            else:
                send_tilt(ser, int(val_str))
        except KeyboardInterrupt:
            break
        except ValueError:
            print("Please enter a number between -45 and +45, or 'max' / '0'")

    ser.close()
    print("\nDone.")


if __name__ == "__main__":
    main()
