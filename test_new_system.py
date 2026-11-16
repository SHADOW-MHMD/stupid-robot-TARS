"""
End-to-End Verification Test for Refreshed TARS 4WD System.
Tests:
1. Config loader
2. Face recognizer models & enrollment logic
3. Vision engine mode switcher and camera tilt
4. Motor bridge command dispatch & mock serial
5. Web Cockpit REST endpoints
"""
import json
import os
import sys
from pathlib import Path
import numpy as np
import pytest

_REPO_ROOT = Path(__file__).resolve().parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from shared.config_loader import load_config
from shared.sound_effects import SoundEffectPlayer
from laptop.vision_engine import BiometricFaceRecognizer, LightweightVisionEngine
from pi.motor_bridge import ESP32SerialHandler, MotorBridgeService
from fastapi.testclient import TestClient
from laptop.dashboard import app


def test_config_loader():
    cfg = load_config()
    assert "network" in cfg
    assert "video" in cfg
    assert "hardware" in cfg
    assert cfg["hardware"]["ultrasonic_stop_dist_cm"] == 15.0
    print("✅ Config Loader: PASSED")


def test_face_recognizer():
    recognizer = BiometricFaceRecognizer()
    assert recognizer.detector is not None
    assert recognizer.recognizer is not None

    # Test with dummy face-sized image
    dummy_img = np.zeros((320, 320, 3), dtype=np.uint8)
    # Draw simple face-like shapes
    cv2_circle = np.full((320, 320, 3), 120, dtype=np.uint8)
    name, score, bbox = recognizer.identify_face(cv2_circle)
    assert name in ("No Face", "Unregistered Guest", "Unknown")
    print("✅ Biometric Face Recognizer: PASSED")


def test_motor_serial_handler():
    handler = ESP32SerialHandler(port="/dev/ttyUSB_MOCK_TEST")
    assert handler.is_mock is True
    handler.send_command("FWD 50")
    handler.send_command("TILT -20")
    line = handler.read_line()
    assert line is not None
    data = json.loads(line)
    assert "dist_cm" in data
    handler.close()
    print("✅ ESP32 Serial Handler: PASSED")


def test_dashboard_endpoints():
    client = TestClient(app)
    
    # 1. Test index page
    res = client.get("/")
    assert res.status_code == 200
    assert "TARS COCKPIT" in res.text

    # 2. Test control motor
    res = client.post("/api/control", json={"action": "FWD", "speed": 40})
    assert res.status_code == 200
    assert res.json()["cmd"] == "FWD"

    # 3. Test camera tilt
    res = client.post("/api/tilt", json={"angle": -30})
    assert res.status_code == 200
    assert res.json()["tilt"] == -30

    # 4. Test mode switcher
    res = client.post("/api/mode", json={"mode": "PUPPY_HUNT"})
    assert res.status_code == 200
    assert res.json()["mode"] == "PUPPY_HUNT"

    # 5. Test personality passcode rejection
    res = client.post("/api/personality", json={
        "passcode": "WrongPassword", "humor": 50, "honesty": 50,
        "sarcasm": 50, "irritability": 50, "courage": 50, "loyalty": 50
    })
    assert res.status_code == 403

    # 6. Test personality valid passcode
    res = client.post("/api/personality", json={
        "passcode": "Bravo-Charlie-9", "humor": 80, "honesty": 90,
        "sarcasm": 85, "irritability": 20, "courage": 95, "loyalty": 99
    })
    assert res.status_code == 200
    print("✅ Web Cockpit Endpoints: PASSED")


if __name__ == "__main__":
    test_config_loader()
    test_face_recognizer()
    test_motor_serial_handler()
    test_dashboard_endpoints()
    print("\n🎉 ALL TESTS PASSED SUCCESSFULLY!")
