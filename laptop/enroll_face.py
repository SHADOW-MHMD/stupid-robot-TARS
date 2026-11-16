"""
TARS Biometric Face Enrollment CLI (laptop/enroll_face.py).
Captures webcam or camera still and enrolls 'Creator Mishal' into assets/faces/faces_db.json.
Usage:
    python3 laptop/enroll_face.py --name "Creator Mishal"
"""
from __future__ import annotations
import argparse
import sys
import time
from pathlib import Path

import cv2

_CURRENT_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _CURRENT_DIR.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from laptop.vision_engine import BiometricFaceRecognizer


def main():
    parser = argparse.ArgumentParser(description="Enroll face into TARS biometric database.")
    parser.add_argument("--name", type=str, default="Creator Mishal", help="Name of person to enroll")
    parser.add_argument("--device", type=int, default=0, help="Webcam device index")
    args = parser.parse_args()

    print("==========================================================")
    print(f"  👤 TARS Biometric Face Enrollment: {args.name}")
    print("==========================================================")

    recognizer = BiometricFaceRecognizer()
    cap = cv2.VideoCapture(args.device)

    if not cap.isOpened():
        print(f"❌ Could not open webcam index {args.device}!")
        sys.exit(1)

    print("Looking at camera... Capturing in 2 seconds...")
    time.sleep(1.0)
    ret, frame = cap.read()
    cap.release()

    if not ret or frame is None:
        print("❌ Failed to capture camera frame!")
        sys.exit(1)

    success, msg = recognizer.enroll_face(args.name, frame)
    if success:
        print(f"✅ SUCCESS: {msg}")
    else:
        print(f"❌ ENROLLMENT FAILED: {msg}")


if __name__ == "__main__":
    main()
