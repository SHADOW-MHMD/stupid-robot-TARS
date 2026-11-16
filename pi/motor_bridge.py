"""
TARS Edge Node: Motor & Telemetry Bridge (pi/motor_bridge.py).
Subscribes to ZeroMQ motor vectors (port 5557) and forwards them to ESP32 serial (/dev/ttyUSB0).
Reads 20 Hz telemetry from ESP32 and publishes it on ZeroMQ (port 5558).
"""
from __future__ import annotations
import argparse
import json
import logging
import os
from pathlib import Path
import sys
import threading
import time

_CURRENT_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _CURRENT_DIR.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from shared.config_loader import load_config
from shared.zmq_utils import ZMQPublisher, ZMQSubscriber
from shared.sound_effects import SoundEffectPlayer

try:
    import serial
except ImportError:
    serial = None

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s: %(message)s")
logger = logging.getLogger("TARS.Pi.MotorBridge")


class ESP32SerialHandler:
    def __init__(self, port: str = "/dev/ttyUSB0", baudrate: int = 115200) -> None:
        self.port = port
        self.baudrate = baudrate
        self.serial_conn = None
        self.is_mock = False
        self._init_connection()

    def _init_connection(self) -> None:
        if serial is None:
            logger.warning("PySerial not installed! Operating in Mock Serial mode.")
            self.is_mock = True
            return

        try:
            self.serial_conn = serial.Serial(self.port, self.baudrate, timeout=0.1)
            time.sleep(1.0)  # Allow ESP32 reset after DTR/RTS
            logger.info(f"Connected to ESP32 on {self.port} @ {self.baudrate}")
        except Exception as e:
            logger.warning(f"Could not open physical serial port {self.port}: {e}. Falling back to Mock Serial.")
            self.is_mock = True

    def send_command(self, cmd_str: str) -> None:
        if not cmd_str.endswith("\n"):
            cmd_str += "\n"

        if self.is_mock:
            logger.info(f"[Mock Serial Out] -> {cmd_str.strip()}")
            return

        try:
            self.serial_conn.write(cmd_str.encode("utf-8"))
            self.serial_conn.flush()
        except Exception as e:
            logger.error(f"Serial write error: {e}")

    def read_line(self) -> str | None:
        if self.is_mock:
            # Return synthetic ultrasonic distance around 45 cm
            return '{"dist_cm": 45.2, "tilt": 0, "cmd": "OK"}'

        try:
            if self.serial_conn:
                line = self.serial_conn.readline().decode("utf-8", errors="replace").strip()
                return line if line else None
        except Exception as e:
            logger.error(f"Serial read error: {e}")
        return None

    def close(self) -> None:
        if self.serial_conn and not self.is_mock:
            try:
                self.serial_conn.close()
            except Exception:
                pass


class MotorBridgeService:
    def __init__(
        self,
        motor_sub_port: int | None = None,
        telemetry_pub_port: int | None = None,
        serial_port: str | None = None,
        laptop_host: str | None = None,
    ) -> None:
        cfg = load_config()
        net_cfg = cfg.get("network", {})
        hw_cfg = cfg.get("hardware", {})

        self.sub_port = motor_sub_port if motor_sub_port is not None else net_cfg.get("motor_port", 5557)
        self.pub_port = telemetry_pub_port if telemetry_pub_port is not None else net_cfg.get("telemetry_port", 5558)
        self.laptop_host = laptop_host if laptop_host is not None else net_cfg.get("laptop_host", "localhost")
        serial_p = serial_port if serial_port is not None else hw_cfg.get("serial_port", "/dev/ttyUSB0")

        self.subscriber = ZMQSubscriber(host=self.laptop_host, port=self.sub_port, topic="")
        self.publisher = ZMQPublisher(port=self.pub_port, host="*")
        self.serial_handler = ESP32SerialHandler(port=serial_p)
        self.running = False
        self.last_cmd_time = time.time()
        self.current_state = "STOP"

    def start(self) -> None:
        self.running = True
        logger.info(f"Motor Bridge Service active: ZMQ In({self.sub_port}) -> Serial -> ZMQ Out({self.pub_port})")

        # Telemetry reader thread
        t_thread = threading.Thread(target=self._telemetry_loop, daemon=True)
        t_thread.start()

        # Command subscriber loop
        self._command_loop()

    def _command_loop(self) -> None:
        while self.running:
            res = self.subscriber.recv_json(timeout_ms=50)
            if res:
                topic, data = res
                self.last_cmd_time = time.time()

                # Check for camera tilt command: {"tilt": -20}
                if "tilt" in data:
                    tilt_deg = int(data["tilt"])
                    self.serial_handler.send_command(f"TILT {tilt_deg}")

                # Check for motor vector: {"cmd": "FWD", "speed": 50}
                if "cmd" in data:
                    action = str(data["cmd"]).upper()
                    speed = int(data.get("speed", 50))
                    
                    if action == "STOP":
                        if self.current_state != "STOP":
                            SoundEffectPlayer.play_pneumatic_brake()
                        self.serial_handler.send_command("STOP 0")
                        self.current_state = "STOP"
                    else:
                        self.serial_handler.send_command(f"{action} {speed}")
                        self.current_state = action

            # Safety Watchdog: If moving and no command in 600ms, stop!
            if self.current_state != "STOP" and (time.time() - self.last_cmd_time > 0.6):
                logger.warning("Motor Bridge safety watchdog triggered: stopping motors.")
                SoundEffectPlayer.play_pneumatic_brake()
                self.serial_handler.send_command("STOP 0")
                self.current_state = "STOP"

    def _telemetry_loop(self) -> None:
        while self.running:
            raw_line = self.serial_handler.read_line()
            if raw_line and raw_line.startswith("{"):
                try:
                    telemetry_data = json.loads(raw_line)
                    self.publisher.send_json("telemetry", telemetry_data)
                except Exception:
                    pass
            time.sleep(0.05)  # 20 Hz rate

    def stop(self) -> None:
        self.running = False
        self.serial_handler.send_command("STOP 0")
        self.serial_handler.close()
        self.subscriber.close()
        self.publisher.close()


def main():
    cfg = load_config()
    net_cfg = cfg.get("network", {})
    hw_cfg = cfg.get("hardware", {})

    service = MotorBridgeService(
        motor_sub_port=net_cfg.get("motor_port", 5557),
        telemetry_pub_port=net_cfg.get("telemetry_port", 5558),
        serial_port=hw_cfg.get("serial_port", "/dev/ttyUSB0"),
    )
    try:
        service.start()
    except KeyboardInterrupt:
        service.stop()


if __name__ == "__main__":
    main()
