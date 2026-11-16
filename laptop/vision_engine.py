"""
TARS Compute Node: Lightweight MediaPipe Vision Engine (laptop/vision_engine.py).
Provides:
- MediaPipe Object Detection ("Puppy Mode" tracking balls, cups, bottles, toys on the floor).
- MediaPipe Pose Tracking (Person Follow Mode).
- MediaPipe Hand Gestures (Open Palm = Follow, Raised Fist = Emergency STOP 0).
- OpenCV YuNet + SFace Biometric Face Recognition ("Creator Mishal" vs "Guest").
- Autonomous Camera Tilt Coordination (tilts down for floor objects, up for faces).
"""
from __future__ import annotations
import argparse
from dataclasses import dataclass
import json
import logging
import math
import os
from pathlib import Path
import sys
import threading
import time
from typing import Any, Dict, List, Optional, Tuple

import cv2
import numpy as np

_CURRENT_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _CURRENT_DIR.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from shared.config_loader import load_config
from shared.zmq_utils import ZMQPublisher, ZMQSubscriber
from shared.sound_effects import SoundEffectPlayer

# Optional MediaPipe import with graceful fallback
try:
    import mediapipe as mp
    MEDIAPIPE_AVAILABLE = True
except ImportError:
    mp = None
    MEDIAPIPE_AVAILABLE = False

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s: %(message)s")
logger = logging.getLogger("TARS.Laptop.VisionEngine")

_ASSETS_DIR = _REPO_ROOT / "assets"
_WEIGHTS_DIR = _ASSETS_DIR / "weights"
_FACES_DB_PATH = _ASSETS_DIR / "faces" / "faces_db.json"
_YUNET_PATH = _WEIGHTS_DIR / "face_detection_yunet_2023mar.onnx"
_SFACE_PATH = _WEIGHTS_DIR / "face_recognition_sface_2021dec.onnx"


class BiometricFaceRecognizer:
    """Real-time biometric face matcher using OpenCV YuNet + SFace."""
    def __init__(self, db_path: Path = _FACES_DB_PATH) -> None:
        self.db_path = db_path
        self.detector = None
        self.recognizer = None
        self.known_faces: Dict[str, np.ndarray] = {}
        self._init_models()
        self.load_database()

    def _init_models(self) -> None:
        if _YUNET_PATH.exists() and _SFACE_PATH.exists():
            try:
                self.detector = cv2.FaceDetectorYN.create(
                    str(_YUNET_PATH), "", (320, 320), score_threshold=0.6, nms_threshold=0.3
                )
                self.recognizer = cv2.FaceRecognizerSF.create(str(_SFACE_PATH), "")
                logger.info("OpenCV YuNet + SFace biometric models loaded successfully.")
            except Exception as e:
                logger.error(f"Failed to initialize YuNet/SFace: {e}")
        else:
            logger.warning(f"Face weights missing in {_WEIGHTS_DIR}. Face recognition running in fallback mode.")

    def load_database(self) -> None:
        if self.db_path.exists():
            try:
                with open(self.db_path, "r", encoding="utf-8") as f:
                    raw = json.load(f)
                    for name, vec in raw.items():
                        self.known_faces[name] = np.array(vec, dtype=np.float32)
                logger.info(f"Loaded {len(self.known_faces)} biometric profile(s) from {self.db_path}")
            except Exception as e:
                logger.error(f"Error loading faces database: {e}")

    def save_database(self) -> None:
        try:
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            data = {name: vec.tolist() for name, vec in self.known_faces.items()}
            with open(self.db_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            logger.info("Faces database saved.")
        except Exception as e:
            logger.error(f"Error saving faces database: {e}")

    def enroll_face(self, name: str, frame_bgr: np.ndarray) -> Tuple[bool, str]:
        if self.detector is None or self.recognizer is None:
            return False, "Face models not loaded."

        h, w = frame_bgr.shape[:2]
        self.detector.setInputSize((w, h))
        faces = self.detector.detect(frame_bgr)
        if faces[1] is None or len(faces[1]) == 0:
            return False, "No face detected in camera frame. Ensure good lighting."

        aligned = self.recognizer.alignCrop(frame_bgr, faces[1][0])
        feature = self.recognizer.feature(aligned)
        self.known_faces[name] = feature.flatten()
        self.save_database()
        return True, f"Successfully enrolled face for: {name}"

    def identify_face(self, frame_bgr: np.ndarray) -> Tuple[str, float, Optional[Tuple[int, int, int, int]]]:
        if self.detector is None or self.recognizer is None or frame_bgr is None:
            return "Unknown", 0.0, None

        h, w = frame_bgr.shape[:2]
        self.detector.setInputSize((w, h))
        faces = self.detector.detect(frame_bgr)
        if faces[1] is None or len(faces[1]) == 0:
            return "No Face", 0.0, None

        face_data = faces[1][0]
        bbox = (int(face_data[0]), int(face_data[1]), int(face_data[2]), int(face_data[3]))
        aligned = self.recognizer.alignCrop(frame_bgr, face_data)
        feature = self.recognizer.feature(aligned)

        best_name = "Unregistered Guest"
        best_score = 0.0

        for name, enrolled_vec in self.known_faces.items():
            score = self.recognizer.match(feature, enrolled_vec.reshape(1, -1), cv2.FaceRecognizerSF_FR_COSINE)
            if score > best_score:
                best_score = score
                if score >= 0.363:  # Recommended SFace cosine threshold
                    best_name = name

        return best_name, float(best_score), bbox


class LightweightVisionEngine:
    def __init__(self) -> None:
        self.config = load_config()
        self.net_cfg = self.config.get("network", {})
        self.nav_cfg = self.config.get("navigation", {})

        self.video_sub = ZMQSubscriber(host=self.net_cfg.get("pi_host", "localhost"), port=self.net_cfg.get("video_port", 5555), topic="")
        self.motor_pub = ZMQPublisher(port=self.net_cfg.get("motor_port", 5557), host="*")
        self.telemetry_sub = ZMQSubscriber(host=self.net_cfg.get("pi_host", "localhost"), port=self.net_cfg.get("telemetry_port", 5558), topic="")

        self.face_recognizer = BiometricFaceRecognizer()
        self.mode = "MANUAL"  # MANUAL, PUPPY_HUNT, FOLLOW, SENTRY
        self.running = False
        self.latest_telemetry: dict[str, Any] = {"dist_cm": 100.0, "tilt": 0}
        self.latest_frame: np.ndarray | None = None
        self.latest_annotated_frame: np.ndarray | None = None
        self._lock = threading.Lock()

        # MediaPipe Solutions
        self.mp_hands = None
        self.mp_pose = None
        self._init_mediapipe()

    def _init_mediapipe(self) -> None:
        if MEDIAPIPE_AVAILABLE and mp and hasattr(mp, "solutions"):
            try:
                self.mp_hands = mp.solutions.hands.Hands(
                    static_image_mode=False, max_num_hands=1, min_detection_confidence=0.5
                )
                self.mp_pose = mp.solutions.pose.Pose(
                    static_image_mode=False, min_detection_confidence=0.5
                )
                logger.info("MediaPipe Hands and Pose initialized.")
            except Exception as e:
                logger.error(f"Error initializing MediaPipe: {e}")

    def set_mode(self, new_mode: str) -> None:
        self.mode = new_mode.upper()
        logger.info(f"Vision Engine mode set to: {self.mode}")
        # Auto-tilt camera based on mode
        if self.mode == "PUPPY_HUNT":
            self.set_camera_tilt(-35)  # Tilt down to scan the floor
        elif self.mode in ("FOLLOW", "SENTRY"):
            self.set_camera_tilt(20)   # Tilt up to observe human faces/gestures
        else:
            self.set_camera_tilt(0)    # Level

    def set_camera_tilt(self, angle_deg: int) -> None:
        self.motor_pub.send_json("motor", {"tilt": angle_deg})

    def send_motor_cmd(self, action: str, speed: int = 45) -> None:
        self.motor_pub.send_json("motor", {"cmd": action, "speed": speed})

    def start(self) -> None:
        self.running = True
        threading.Thread(target=self._telemetry_listener, daemon=True).start()
        threading.Thread(target=self._vision_loop, daemon=True).start()
        logger.info("Lightweight Vision Engine running.")

    def _telemetry_listener(self) -> None:
        while self.running:
            res = self.telemetry_sub.recv_json(timeout_ms=50)
            if res:
                topic, data = res
                if isinstance(data, dict):
                    with self._lock:
                        self.latest_telemetry.update(data)
                        if "dist_cm" in data:
                            self.front_dist_cm = float(data["dist_cm"])

    def _vision_loop(self) -> None:
        while self.running:
            parts = self.video_sub.recv_multipart(timeout_ms=50)
            if not parts or len(parts) < 2:
                continue

            jpeg_bytes = parts[1]
            frame = cv2.imdecode(np.frombuffer(jpeg_bytes, dtype=np.uint8), cv2.IMREAD_COLOR)
            if frame is None:
                continue

            annotated = frame.copy()
            h, w = frame.shape[:2]

            # 1. Biometric Face Identification Check
            name, score, bbox = self.face_recognizer.identify_face(frame)
            if bbox:
                bx, by, bw, bh = bbox
                color = (0, 255, 0) if "Creator" in name else (0, 200, 255)
                cv2.rectangle(annotated, (bx, by), (bx + bw, by + bh), color, 2)
                cv2.putText(annotated, f"{name} ({score:.2f})", (bx, by - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)

            # 2. Hand Gestures Check (MediaPipe)
            if self.mp_hands:
                rgb_f = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                hand_res = self.mp_hands.process(rgb_f)
                if hand_res.multi_hand_landmarks:
                    for lms in hand_res.multi_hand_landmarks:
                        mp.solutions.drawing_utils.draw_landmarks(annotated, lms, mp.solutions.hands.HAND_CONNECTIONS)
                        # Check Open Palm vs Raised Fist
                        # Index tip vs MCP
                        index_tip_y = lms.landmark[8].y
                        index_mcp_y = lms.landmark[5].y
                        wrist_y = lms.landmark[0].y

                        if index_tip_y > index_mcp_y:
                            # Fingers curled down -> Raised Fist (EMERGENCY STOP)
                            cv2.putText(annotated, "GESTURE: RAISED FIST (HALT)", (30, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
                            self.send_motor_cmd("STOP", 0)
                        elif index_tip_y < index_mcp_y < wrist_y:
                            # Fingers extended up -> Open Palm (FOLLOW)
                            cv2.putText(annotated, "GESTURE: OPEN PALM (FOLLOW)", (30, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
                            if self.mode != "FOLLOW":
                                self.set_mode("FOLLOW")

            # 3. Mode-Specific Autonomous Navigation
            if self.mode == "PUPPY_HUNT":
                self._handle_puppy_hunt(frame, annotated)
            elif self.mode == "FOLLOW":
                self._handle_person_follow(frame, annotated)

            # Draw HUD
            cv2.putText(annotated, f"MODE: {self.mode} | DIST: {self.front_dist_cm:.1f}cm", (10, h - 20), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)

            with self._lock:
                self.latest_frame = frame
                self.latest_annotated_frame = annotated

    def _handle_puppy_hunt(self, frame: np.ndarray, annotated: np.ndarray) -> None:
        """Puppy Mode: Detects high-contrast floor objects (e.g. green/red balls or toys) & approaches."""
        h, w = frame.shape[:2]
        # Fast color blob detector for colorful toys/balls on floor
        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
        
        # Color mask: Vibrant Green / Orange / Red ball detection
        mask1 = cv2.inRange(hsv, np.array([35, 80, 80]), np.array([85, 255, 255]))    # Green
        mask2 = cv2.inRange(hsv, np.array([0, 100, 100]), np.array([15, 255, 255]))   # Red/Orange
        mask = cv2.bitwise_or(mask1, mask2)
        
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if contours:
            largest = max(contours, key=cv2.contourArea)
            if cv2.contourArea(largest) > 400:
                ((cx, cy), radius) = cv2.minEnclosingCircle(largest)
                cv2.circle(annotated, (int(cx), int(cy)), int(radius), (255, 0, 255), 3)
                cv2.putText(annotated, "TARGET BALL", (int(cx - 30), int(cy - 10)), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 0, 255), 2)

                center_x = w / 2.0
                deadzone = w * 0.15

                # Front obstacle / inspection distance check via ultrasonic
                if self.front_dist_cm <= 15.0:
                    cv2.putText(annotated, "SNIFF INSPECTION (REACHED)", (int(cx - 50), int(cy + 30)), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
                    self.send_motor_cmd("STOP", 0)
                else:
                    # Steering towards ball
                    if cx < (center_x - deadzone):
                        self.send_motor_cmd("LEFT", 35)
                    elif cx > (center_x + deadzone):
                        self.send_motor_cmd("RIGHT", 35)
                    else:
                        self.send_motor_cmd("FWD", 45)
                return

        # If no ball seen, idle stop
        self.send_motor_cmd("STOP", 0)

    def _handle_person_follow(self, frame: np.ndarray, annotated: np.ndarray) -> None:
        """Follow Mode: Follows detected person torso position."""
        if not self.mp_pose:
            return
        h, w = frame.shape[:2]
        rgb_f = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        pose_res = self.mp_pose.process(rgb_f)

        if pose_res.pose_landmarks:
            mp.solutions.drawing_utils.draw_landmarks(annotated, pose_res.pose_landmarks, mp.solutions.pose.POSE_CONNECTIONS)
            nose = pose_res.pose_landmarks.landmark[0]
            cx = nose.x * w
            center_x = w / 2.0
            deadzone = w * 0.15

            if self.front_dist_cm <= 12.0:
                # Target walked too close: politely retreat and yield space
                self.send_motor_cmd("BWD", 35)
            elif self.front_dist_cm <= 25.0:
                self.send_motor_cmd("STOP", 0)
            else:
                if cx < (center_x - deadzone):
                    self.send_motor_cmd("LEFT", 35)
                elif cx > (center_x + deadzone):
                    self.send_motor_cmd("RIGHT", 35)
                else:
                    self.send_motor_cmd("FWD", 40)
            return

        self.send_motor_cmd("STOP", 0)

    def stop(self) -> None:
        self.running = False
        self.send_motor_cmd("STOP", 0)
        self.video_sub.close()
        self.motor_pub.close()
        self.telemetry_sub.close()


def main():
    engine = LightweightVisionEngine()
    engine.start()
    try:
        while True:
            time.sleep(1.0)
    except KeyboardInterrupt:
        engine.stop()


if __name__ == "__main__":
    main()
