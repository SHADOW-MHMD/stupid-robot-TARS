# TARS: Distributed Dual-Brain Autonomous Mobile Robot

An autonomous, multimodal mobile robot inspired by TARS from *Interstellar*, featuring real-time conversational voice interaction via **Google Gemini Live API**, vision and biometric tracking via **MediaPipe** and **OpenCV YuNet/SFace**, and low-level reflex control powered by an **ESP32** microcontroller.

---

## 🏛️ System Architecture

TARS utilizes a distributed dual-brain architecture to split edge voice I/O, heavy vision processing, and physical actuation across dedicated nodes:

```
                          +------------------------+
                          |    Google Gemini Live  |
                          |   (Bidirectional Audio)|
                          +-----------+------------+
                                      ^
                        PCM Audio /   |  TTS Audio /
                        1 FPS Frames  |  Tool Calls
                                      v
+------------------------+   ZeroMQ   +------------------------+
|  Laptop Compute Node   | <--------> |  Raspberry Pi 4B Node  |
|  (MediaPipe / Vision)  |  Port 5556 |  (Voice & Safety Brain)|
+------------------------+            +-----------+------------+
                                                  | Emergency Serial
                                                  | STOP 0 / Failsafe
                                                  v
                                      +------------------------+
                                      |   ESP32 Actuation Node |
                                      |   (4WD Motors / Sonar) |
                                      +------------------------+
```

### 1. Raspberry Pi Edge Node (`pi/`)
* **Gemini Live Client (`chat_brain.py`)**: Bidirectional streaming using `google-genai` SDK (`gemini-3.1-flash-live-preview` / `gemini-3.8-live`).
* **Audio DSP**: 16kHz 16-bit mono PCM capture with software gain, 24kHz speaker playback with instant (<20ms) barge-in / interruption flush.
* **Echo Suppression**: Half-duplex dither injection during TTS output to eliminate acoustic feedback.
* **Safety Watchdog**: Monitors laptop heartbeat; executes direct hardware `STOP 0` over USB serial if heartbeat drops for >500ms during active navigation.
* **Video Streamer (`video_streamer.py`)**: ZeroMQ publisher broadcasting camera frames at port 5555.

### 2. Laptop Compute Node (`laptop/`)
* **Vision Engine (`vision_engine.py`)**:
  * **Puppy Mode**: MediaPipe object detection tracking balls, cups, and toys on the floor.
  * **Person Following**: MediaPipe Pose estimation with adaptive center-of-mass PID tracking.
  * **Hand Gestures**: Open Palm to follow, Raised Fist for reflex emergency stop.
  * **Biometric Face Recognition**: Real-time OpenCV YuNet detector + SFace recognizer ("Creator Mishal" vs "Guest").
  * **Camera Tilt**: Coordinates SG90 micro-servo angles (downwards for floor objects, level for faces).
* **Web Cockpit (`dashboard.py`)**: FastAPI & Tailwind web telemetry interface with touch joystick and personality sliders.

### 3. ESP32 Actuation Node (`esp32/`)
* **Firmware (`esp32/src/main.cpp` & `esp32/tars_firmware.ino`)**:
  * 4WD differential drive via L298N (HW-095) with 20 kHz ultrasonic PWM.
  * Front HC-SR04 ultrasonic sensor with hard reflex auto-avoidance (<15 cm).
  * 50 Hz camera tilt micro-servo pulse generator.
  * 115200 baud USB serial command dispatcher and 20 Hz JSON telemetry emitter.

---

## 🚀 Getting Started

### 1. Prerequisites
* **Python**: Python 3.10+ (tested on Python 3.11 / 3.12 / 3.14)
* **Hardware**:
  * Raspberry Pi 4B (or 5) with USB microphone and speaker
  * ESP32 DevKit V1 connected via USB (`/dev/ttyUSB0`)
  * L298N Motor Driver + 4x DC Motors
  * HC-SR04 Ultrasonic Sensor + SG90 Servo

### 2. Installation

Clone the repository and install dependencies:
```bash
git clone https://github.com/SHADOW-MHMD/stupid-robot-TARS.git
cd stupid-robot-TARS

# On Laptop Compute Node:
pip install -r requirements.txt

# On Raspberry Pi Edge Node:
pip install -r requirements-pi.txt
```

### 3. Configuration

Copy the example configuration:
```bash
cp config.example.json config.json
```
Set your Gemini API key:
```bash
export GEMINI_API_KEY="your-gemini-api-key"
```
*(Or specify it directly inside `config.json`)*.

---

## 🎮 Running TARS

### 1. Flash ESP32 Firmware
Using PlatformIO or Arduino IDE:
```bash
cd esp32
pio run --target upload
```

### 2. Start Raspberry Pi Edge Node
```bash
cd pi
bash run.sh
```

### 3. Start Laptop Compute Node & Web Dashboard
```bash
cd laptop
bash run.sh
```
Open your browser to `http://localhost:8000` to access the TARS Cockpit.

---

## 🛡️ License
MIT License. Built with passion by Mishal.
