"""
TARS Compute Node: OLED Black Web Cockpit (laptop/dashboard.py).
FastAPI application serving:
- Low-latency MJPEG video streaming.
- 20 Hz WebSocket live telemetry HUD.
- WASD keyboard teleoperation & Mobile touch virtual joystick with dead-man failsafe.
- Camera Tilt slider.
- 1-Click Mode Switcher (MANUAL, PUPPY_HUNT, FOLLOW, SENTRY).
- 6-Axis Personality Matrix with 'Bravo-Charlie-9' authentication.
"""
from __future__ import annotations
import asyncio
import json
import logging
import os
from pathlib import Path
import sys
import time
from typing import Any, Dict

import cv2
from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
import uvicorn

_CURRENT_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _CURRENT_DIR.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from shared.config_loader import load_config
from shared.zmq_utils import ZMQPublisher, ZMQSubscriber
from laptop.vision_engine import LightweightVisionEngine

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s: %(message)s")
logger = logging.getLogger("TARS.Laptop.Dashboard")

app = FastAPI(title="TARS OLED Black Web Cockpit", version="2.0")
templates = Jinja2Templates(directory=str(_CURRENT_DIR / "templates"))

# Global Engine & Networking
cfg = load_config()
net_cfg = cfg.get("network", {})
vision_engine = LightweightVisionEngine()


class MotionCommand(BaseModel):
    action: str
    speed: int = 50


class JoystickCommand(BaseModel):
    x: float
    y: float
    speed: int = 50


class TiltCommand(BaseModel):
    angle: int


class ModeCommand(BaseModel):
    mode: str


class PersonalityUpdate(BaseModel):
    passcode: str
    humor: int
    honesty: int
    sarcasm: int
    irritability: int
    courage: int
    loyalty: int


@app.on_event("startup")
def startup_event():
    vision_engine.start()
    logger.info("Vision Engine started in Dashboard.")


@app.on_event("shutdown")
def shutdown_event():
    vision_engine.stop()


@app.get("/", response_class=HTMLResponse)
async def get_index(request: Request):
    return templates.TemplateResponse(request=request, name="index.html", context={"config": cfg})


def generate_mjpeg_frames():
    while True:
        with vision_engine._lock:
            frame = vision_engine.latest_annotated_frame

        if frame is not None:
            ret, buffer = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 70])
            if ret:
                yield (b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + buffer.tobytes() + b"\r\n")
        time.sleep(0.06)  # ~16 FPS stream


@app.get("/video_feed")
async def video_feed():
    return StreamingResponse(generate_mjpeg_frames(), media_type="multipart/x-mixed-replace; boundary=frame")


@app.post("/api/control")
async def control_motors(cmd: MotionCommand):
    act = cmd.action.upper()
    spd = max(0, min(100, cmd.speed))
    vision_engine.send_motor_cmd(act, spd)
    return {"status": "ok", "cmd": act, "speed": spd}


@app.post("/api/joystick")
async def joystick_control(cmd: JoystickCommand):
    # Dead-man stop check
    if abs(cmd.x) < 0.1 and abs(cmd.y) < 0.1:
        vision_engine.send_motor_cmd("STOP", 0)
        return {"status": "ok", "cmd": "STOP"}

    spd = max(0, min(100, cmd.speed))
    # Vector translation to differential drive
    if abs(cmd.y) >= abs(cmd.x):
        action = "FWD" if cmd.y > 0 else "BWD"
    else:
        action = "RIGHT" if cmd.x > 0 else "LEFT"

    vision_engine.send_motor_cmd(action, spd)
    return {"status": "ok", "cmd": action, "speed": spd}


@app.post("/api/tilt")
async def tilt_camera(cmd: TiltCommand):
    angle = max(-45, min(35, cmd.angle))
    vision_engine.set_camera_tilt(angle)
    return {"status": "ok", "tilt": angle}


@app.post("/api/mode")
async def set_mode(cmd: ModeCommand):
    new_mode = cmd.mode.upper()
    vision_engine.set_mode(new_mode)
    return {"status": "ok", "mode": new_mode}


@app.post("/api/personality")
async def update_personality(p: PersonalityUpdate):
    expected = cfg.get("personality", {}).get("authorization_code", "Bravo-Charlie-9")
    if p.passcode != expected:
        raise HTTPException(status_code=403, detail="Invalid authorization passcode! Access denied.")

    # Update personality
    pers = cfg.setdefault("personality", {})
    pers["humor_level"] = p.humor
    pers["honesty_level"] = p.honesty
    pers["sarcasm_level"] = p.sarcasm
    pers["irritability_level"] = p.irritability
    pers["courage_level"] = p.courage
    pers["loyalty_level"] = p.loyalty

    # Atomic save to config.json
    try:
        tmp_cfg = _REPO_ROOT / "config.json.tmp"
        with open(tmp_cfg, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2)
        os.replace(tmp_cfg, _REPO_ROOT / "config.json")
    except Exception as e:
        logger.error(f"Error saving config: {e}")

    logger.info(f"Personality updated: Humor={p.humor}, Honesty={p.honesty}, Sarcasm={p.sarcasm}")
    return {"status": "ok", "message": "Personality matrix updated successfully."}


@app.websocket("/ws/telemetry")
async def ws_telemetry(websocket: WebSocket):
    await websocket.accept()
    try:
        while True:
            # Non-blocking thread-safe telemetry read from vision engine
            with vision_engine._lock:
                telemetry = dict(vision_engine.latest_telemetry)
            telemetry["front_dist_cm"] = vision_engine.front_dist_cm
            telemetry["mode"] = vision_engine.mode

            await websocket.send_text(json.dumps(telemetry))
            await asyncio.sleep(0.05)  # 20 Hz non-blocking push
    except WebSocketDisconnect:
        pass


def main():
    dashboard_cfg = cfg.get("network", {})
    host = dashboard_cfg.get("dashboard_host", "0.0.0.0")
    port = dashboard_cfg.get("dashboard_port", 8000)
    logger.info(f"Starting TARS Web Cockpit on http://{host}:{port}")
    uvicorn.run(app, host=host, port=port, log_level="warning")


if __name__ == "__main__":
    main()
