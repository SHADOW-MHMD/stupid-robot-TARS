# Project: TARS Dual-Brain Autonomous Mobile Robot Upgrade

## Architecture
- **Distributed Dual-Brain Mono-repo**:
  - **Edge Node (Raspberry Pi)**: Camera capture (`pi/video_streamer.py`), Gemini Live Audio Brain (`pi/chat_brain.py`), Edge `openWakeWord` standby listener, ALSA audio I/O, GPIO Traffic Light controller, pass-through motor serial router (`pi/motor_receiver.py`).
  - **Compute Node (Laptop)**: OpenVINO YOLO11n + ByteTrack + HSV Target Tracker (`laptop/vision_engine.py`), MediaPipe Hand Gesture Recognizer, Async Background Face Recognition Worker, Spatial Landmark Association Engine, Navigation Controller (`laptop/nav_controller.py`), Interstellar FastAPI Web Cockpit (`laptop/dashboard.py`).
  - **Actuation Node (ESP32 / Serial)**: Motor driver and ultrasonic sensor hub.
  - **Shared Engine (`shared/`)**: ZeroMQ Networking (`shared/zmq_utils.py`), Zero-Wear RAM State Engine & Cloudflare D1 Sync (`shared/d1_sync.py`), Telegram Bot API & Remote Command Handler (`shared/telegram_bot.py`), Sound Effects & SFX Waveform Synthesizers (`shared/sound_effects.py`), Cognitive Memory & Landmark Storage (`shared/memory_manager.py`).

## Feature Inventory
| # | Feature | Description | Milestone | Source |
|---|---------|-------------|-----------|--------|
| 1 | OLED Black Web Cockpit | OLED Black / Slate-900 FastAPI Dashboard at `http://localhost:8000` | M3 | R1 |
| 2 | Desktop WASD Driving | WASD keyboard teleoperation with 0-100% speed limiter & crosshairs HUD | M3 | R1 |
| 3 | Mobile Virtual Joystick | Nipple.js / Canvas touch joystick emitting normalized `[-1.0, 1.0]` vectors | M3 | R1 |
| 4 | Dead-Man Failsafe | Instantaneous motor halt (`STOP 0`) on touch release / pointer cancel | M3 | R1 |
| 5 | Live Telemetry HUD | 20 Hz WebSocket push of battery voltage, motor load, ultrasonic distance | M3 | R1 |
| 6 | Miller's Planet Time Dilation | Real-time ZMQ ping latency HUD, styling >200ms latency with time dilation alert | M3 | R1 |
| 7 | Operation Mode Switcher | Switcher for 5 modes (Manual, YOLO Follow, Sentry, Gesture, Inauguration) | M3 | R1 |
| 8 | 6-Axis Personality Sliders | Sliders for Humor, Honesty, Sarcasm, Irritability, Courage, Loyalty | M3 | R1 |
| 9 | Bravo-Charlie-9 Passcode Auth | Passcode verification modal required to persist personality changes | M3 | R1 |
| 10 | Sentry Vision Detection | YOLO person detection in Sentry mode with 5s debounce cooldown | M1, M2, M3 | R2 |
| 11 | Simulated White Strobe Alert | High-frequency LED and UI visual strobe upon sentry breach | M1, M3 | R2 |
| 12 | Security Challenge Speech | Voice challenge playback upon sentry breach | M1, M4 | R2 |
| 13 | Async Photo Telegram Dispatch | Capture uncompressed still and dispatch alert payload to Telegram Bot API | M1, M4 | R2 |
| 14 | Telegram `/locate` Command | Remote command triggering acoustic sonar ping SFX and LED strobe beacon | M1 | R2 |
| 15 | Telegram `/status` Command | Remote command returning live system telemetry snapshot | M1 | R2 |
| 16 | Telegram `/memory` Command | Remote command returning latest cognitive diary logs | M1 | R2 |
| 17 | Zero-Wear RAM State Engine | 0ms read/write caching in Python RAM to eliminate SD card wear | M1 | R3 |
| 18 | Cloudflare D1 Sync Worker | 5s background async flush to Cloudflare D1 (`40097aa95e8d6ea862375a04a24e048f`) | M1 | R3 |
| 19 | Instant Boot Hydration | Fast hydration of state and landmarks from D1/cache in <200ms on startup | M1 | R3 |
| 20 | D1 / SQLite Tables Schema | Schemas for `personality_matrix`, `landmark_memory`, `sentry_incidents` | M1 | R3 |
| 21 | Voice Solver Trigger & Freeze | "TARS, solve this diagram/equation" voice trigger + instant chassis freeze | M4 | R4 |
| 22 | Non-blocking 5MP Still Capture | `capture_high_res_still` on Pi camera without interrupting 10 FPS ZMQ stream | M4 | R4 |
| 23 | Gemini Multimodal Reasoning | Submits 5MP still to Gemini API with reasoning prompt for math/diagrams | M4 | R4 |
| 24 | Native Gemini Audio Output | Synthesized reasoning output played back with native Gemini audio | M4 | R4 |
| 25 | Async Face Recognition Worker | Person crop face recognition every ~2s with 0ms impact on tracking loop | M2 | R5 |
| 26 | Personalized Greeting Matrix | Creator Mishal >85% match confidence vs Unregistered guests | M2 | R5 |
| 27 | Spatial Landmark Memory | Associates detected tools/items with nearest room landmarks + recall | M1, M2 | R5 |
| 28 | MediaPipe Hand Gestures | Open Palm (follow mode), Raised Fist (emergency stop `STOP 0`) | M2 | R6 |
| 29 | `--test-gesture` CLI Runner | Standalone verification runner for MediaPipe hand gesture recognition | M2 | R6 |
| 30 | Edge `openWakeWord` Standby | Local "Hey TARS" listener on Pi to sleep/wake Gemini Live WebSocket session | M4 | R6 |
| 31 | Pneumatic Brake Release SFX | Synthesized air-brake hiss waveform played on motor `STOP 0` | M1 | R6 |
| 32 | Acoustic Sonar Ping Generator | Synthesized 1200 Hz high-Q resonant sonar ping waveform generator | M1 | R6 |
| 33 | Silent Inauguration Observation | Strict TTS mute and locked autonomous navigation during ceremony | M4 | R7 |
| 34 | Ceremony Hotkey & Respectful Yield | Fanfare speech hotkey + `BWD 30` 1.5s yield maneuver -> `STOP 0` | M3, M4 | R7 |
| 35 | D1 CLI Test Verification | `python3 -m shared.d1_sync --test` CLI verification test | M1, M5 | Test |
| 36 | Telegram Bot CLI Verification | `python3 -m shared.telegram_bot --test` CLI verification test | M1, M5 | Test |
| 37 | Gesture CLI Test Verification | `python3 laptop/vision_engine.py --test-gesture` CLI verification test | M2, M5 | Test |
| 38 | Automated E2E Test Suite | Comprehensive multi-tier opaque-box and integration test suite (Tiers 1-4) | M5 | Test |
| 39 | Adversarial Coverage Hardening | White-box gap analysis, edge case stress testing, adversarial hardening | M6 | Test |

## Milestones
| # | Name | Scope | Dependencies | Status |
|---|------|-------|-------------|--------|
| M1 | Cloudflare D1 Sync & Telegram Bot Alert Engine | `shared/d1_sync.py`, `shared/telegram_bot.py`, `shared/sound_effects.py`, `shared/memory_manager.py` | none | DONE |
| M2 | Vision Intelligence & Gesture Control | `laptop/vision_engine.py`, MediaPipe gestures, `--test-gesture`, async face recognition, spatial landmark tracker | M1 | DONE |
| M3 | Interstellar PC & Mobile Web Cockpit | `laptop/dashboard.py`, OLED Black UI, Joystick Dead-Man, Telemetry HUD, Miller's Planet alert, Passcode modal, Ceremony hotkey | M1 | DONE |
| M4 | Multimodal Visual Solver & Edge Audio Brain | `pi/video_streamer.py` (5MP still), `pi/chat_brain.py` (multimodal solver, native audio, openWakeWord, ceremony mute) | M1 | DONE |
| M5 | Automated E2E Test Suite & Integration Pass | `tests/`, `run_tests.py`, Tiers 1-4 comprehensive test suite passing 100% | M1, M2, M3, M4 | DONE |
| M6 | Adversarial Hardening & Final Victory Audit | Tier 5 white-box coverage hardening, stress tests, Forensic Victory Audit | M5 | DONE |

## Interface Contracts

### 1. Zero-Wear RAM State Engine & Cloudflare D1 (`shared/d1_sync.py`)
- `D1SyncEngine(account_id="40097aa95e8d6ea862375a04a24e048f", database_id=None, api_token=None)`
- `update_telemetry(data: dict) -> None`: 0ms in-memory cache update.
- `update_personality(matrix: dict) -> bool`: Updates in-memory matrix and stages for D1 flush.
- `log_landmark_sighting(item: str, landmark: str, dist_px: float, metadata: dict) -> None`: In-memory insert.
- `log_sentry_incident(incident_type: str, confidence: float, snapshot_path: str = None) -> None`: In-memory insert.
- `hydrate_on_boot(timeout_ms: float = 200.0) -> dict`: Fast boot hydration.
- `flush_sync_worker()`: Background worker flushing dirty batches every 5.0 seconds.
- CLI entry: `python3 -m shared.d1_sync --test` -> returns exit code 0.

### 2. Telegram Bot API Integration (`shared/telegram_bot.py`)
- `TelegramBotClient(bot_token=None, chat_id=None)`
- `async send_sentry_alert(photo_bytes_or_path, caption: str, metadata: dict) -> bool`: Async non-blocking photo + alert dispatch.
- `register_command_handler(command: str, handler_callable) -> None`: Remote command router for `/locate`, `/status`, `/memory`.
- CLI entry: `python3 -m shared.telegram_bot --test` -> returns exit code 0.

### 3. Sound Effects & Waveform Generators (`shared/sound_effects.py`)
- `generate_pneumatic_brake_wav(filepath: str = "assets/pneumatic_brake.wav") -> str`: Sci-fi air-release hiss.
- `generate_sonar_ping_wav(filepath: str = "assets/sonar_ping.wav", freq: float = 1200.0) -> str`: 1200 Hz acoustic ping.
- `SoundEffectPlayer.play_pneumatic_brake()`
- `SoundEffectPlayer.play_sonar_ping()`
- `SoundEffectPlayer.play_inauguration_speech()`

### 4. Vision Engine & Gesture Classifier (`laptop/vision_engine.py`)
- `HandGestureRecognizer.classify_gesture(landmarks: list) -> str`: Emits `OPEN_PALM`, `RAISED_FIST`, or `NO_GESTURE`.
- `FaceRecognitionWorker`: Async queue worker processing bbox crops every ~2s (Creator Mishal >85% vs Unregistered Guest).
- `SpatialLandmarkTracker.associate_landmarks(detected_objects: list) -> list`: Associates tools with closest room landmark.
- CLI entry: `python3 laptop/vision_engine.py --test-gesture` -> returns exit code 0.

### 5. Web Cockpit Endpoints (`laptop/dashboard.py`)
- `GET /`: OLED Black / Slate-900 responsive Web Cockpit.
- `WS /ws/telemetry`: 20 Hz telemetry push with battery voltage, motor load, ultrasonic proximity, and ZMQ ping latency.
- `POST /api/control`: WASD manual driving scaled by speed limiter.
- `POST /api/joystick`: Mobile touch joystick receiving normalized vectors `[-1.0, 1.0]` with Dead-Man stop on release.
- `POST /api/mode`: Sets mode (`MANUAL`, `YOLO_FOLLOW`, `SENTRY`, `GESTURE`, `INAUGURATION`).
- `POST /api/personality`: Sets 6-axis personality parameters with passcode `Bravo-Charlie-9`.
- `POST /api/ceremony/climax`: Fanfare speech + Respectful Yield reverse maneuver.

### 6. Edge Video Streamer & Chat Brain (`pi/`)
- `VideoStreamer.capture_high_res_still() -> bytes`: On-demand 5MP still frame capture without interrupting 10 FPS ZMQ stream.
- `ChatBrain.solve_visual_problem(question: str) -> str`: Multimodal equation/diagram solver tool.
- `ChatBrain` edge wake-word listener ("Hey TARS") for sleep/wake of Gemini Live session.

## Code Layout
```
/home/Mishal/robot/TARS/
├── config.json
├── shared/
│   ├── __init__.py
│   ├── zmq_utils.py
│   ├── d1_sync.py
│   ├── telegram_bot.py
│   ├── sound_effects.py
│   ├── memory_manager.py
│   └── gpio_traffic_light.py
├── laptop/
│   ├── __init__.py
│   ├── vision_engine.py
│   ├── nav_controller.py
│   ├── dashboard.py
│   └── templates/
│       └── index.html
├── pi/
│   ├── __init__.py
│   ├── video_streamer.py
│   ├── chat_brain.py
│   └── motor_receiver.py
├── assets/
│   ├── chirp_processing.wav
│   ├── inauguration_speech.wav
│   ├── pneumatic_brake.wav
│   └── sonar_ping.wav
├── tests/
│   ├── __init__.py
│   ├── test_d1_sync.py
│   ├── test_telegram_bot.py
│   ├── test_vision_gestures.py
│   ├── test_cockpit_api.py
│   ├── test_multimodal_solver.py
│   └── test_e2e_scenarios.py
└── run_tests.py
```
