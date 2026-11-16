"""
Lightweight Video Streamer for TARS Raspberry Pi Edge Node.
Captures camera frames, compresses to JPEG, and publishes via ZeroMQ (port 5555).
"""
from __future__ import annotations
import argparse
import logging
import os
from pathlib import Path
import sys
import threading
import time
import cv2
import numpy as np

_CURRENT_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _CURRENT_DIR.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from shared.config_loader import load_config
from shared.zmq_utils import ZMQPublisher

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s: %(message)s")
logger = logging.getLogger("TARS.Pi.VideoStreamer")


class VideoStreamer:
    def __init__(self, port: int = 5555, device_index: int = 0, fps: int = 10, width: int = 640, height: int = 480) -> None:
        self.port = port
        self.device_index = device_index
        self.fps = fps
        self.width = width
        self.height = height
        self.running = False
        self.publisher = ZMQPublisher(port=self.port, host="*")
        self.latest_frame: np.ndarray | None = None
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        self.running = True
        self._thread = threading.Thread(target=self._capture_loop, daemon=True)
        self._thread.start()
        logger.info(f"Video Streamer started on port {self.port} at {self.fps} FPS ({self.width}x{self.height})")

    def stop(self) -> None:
        self.running = False
        if self._thread:
            self._thread.join(timeout=1.0)
        self.publisher.close()
        logger.info("Video Streamer stopped.")

    def get_latest_still(self) -> np.ndarray | None:
        with self._lock:
            return self.latest_frame.copy() if self.latest_frame is not None else None

    def _capture_loop(self) -> None:
        import shutil
        import subprocess

        rpicam_bin = shutil.which("rpicam-vid") or shutil.which("libcamera-vid")
        if rpicam_bin:
            logger.info(f"Using Raspberry Pi hardware CSI camera via {rpicam_bin} (MJPEG)")
            cmd = [
                rpicam_bin,
                "-t", "0",
                "--codec", "mjpeg",
                "--width", str(self.width),
                "--height", str(self.height),
                "--framerate", str(self.fps),
                "-o", "-",
                "--nopreview",
            ]
            try:
                proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, bufsize=65536)
                buf = bytearray()
                while self.running and proc.poll() is None:
                    chunk = proc.stdout.read(4096)
                    if not chunk:
                        break
                    buf.extend(chunk)
                    while True:
                        soi = buf.find(b"\xff\xd8")
                        if soi == -1:
                            buf.clear()
                            break
                        eoi = buf.find(b"\xff\xd9", soi + 2)
                        if eoi == -1:
                            if soi > 0:
                                buf = buf[soi:]
                            break
                        jpeg_bytes = bytes(buf[soi:eoi+2])
                        buf = buf[eoi+2:]

                        frame = cv2.imdecode(np.frombuffer(jpeg_bytes, dtype=np.uint8), cv2.IMREAD_COLOR)
                        if frame is not None:
                            with self._lock:
                                self.latest_frame = frame
                        self.publisher.send_multipart([b"video", jpeg_bytes])

                if proc.poll() is None:
                    proc.terminate()
                return
            except Exception as e:
                logger.warning(f"rpicam-vid streaming failed: {e}; falling back to standard VideoCapture.")

        # Fallback to standard OpenCV VideoCapture (for USB webcams or laptop testing)
        cap = cv2.VideoCapture(self.device_index)
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
        cap.set(cv2.CAP_PROP_FPS, self.fps)

        if not cap.isOpened():
            logger.warning(f"Hardware camera on index {self.device_index} not found! Using synthetic fallback stream.")

        encode_param = [int(cv2.IMWRITE_JPEG_QUALITY), 75]
        interval = 1.0 / max(1, self.fps)

        while self.running:
            start_t = time.time()
            frame = None

            if cap.isOpened():
                ret, raw_frame = cap.read()
                if ret and raw_frame is not None:
                    frame = raw_frame
                else:
                    logger.warning("Camera read dropped a frame.")

            if frame is None:
                # Generate clean synthetic test card with timestamp
                frame = np.zeros((self.height, self.width, 3), dtype=np.uint8)
                cv2.putText(frame, "TARS SYNTHETIC CAMERA STREAM", (50, 100), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
                cv2.putText(frame, time.strftime("%Y-%m-%d %H:%M:%S"), (50, 150), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (200, 200, 200), 1)
                cv2.circle(frame, (320, 320), 40, (0, 200, 50), -1)
                cv2.putText(frame, "Test Ball", (290, 325), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 1)

            with self._lock:
                self.latest_frame = frame

            success, jpeg_bytes = cv2.imencode(".jpg", frame, encode_param)
            if success:
                self.publisher.send_multipart([b"video", jpeg_bytes.tobytes()])

            elapsed = time.time() - start_t
            sleep_t = interval - elapsed
            if sleep_t > 0:
                time.sleep(sleep_t)

        cap.release()


def main():
    cfg = load_config()
    vid_cfg = cfg.get("video", {})
    net_cfg = cfg.get("network", {})

    streamer = VideoStreamer(
        port=net_cfg.get("video_port", 5555),
        device_index=vid_cfg.get("device_index", 0),
        fps=vid_cfg.get("fps", 10),
        width=vid_cfg.get("width", 640),
        height=vid_cfg.get("height", 480),
    )

    streamer.start()
    try:
        while True:
            time.sleep(1.0)
    except KeyboardInterrupt:
        streamer.stop()


if __name__ == "__main__":
    main()
