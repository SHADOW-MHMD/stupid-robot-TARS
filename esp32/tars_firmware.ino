/*
  ==============================================================================
  TARS 4WD Autonomous Robot — ESP32 Actuation Firmware
  Target: DOIT ESP32 DEVKIT V1 / NodeMCU-32S
  Hardware:
    - HW-095 (L298N) 4WD H-Bridge Motor Driver
    - Front Ultrasonic HC-SR04 Sensor (Reflex Auto-Avoidance)
    - Camera Tilt Micro-Servo (SG90 / MG90S)
    - USB Serial Bridge to Raspberry Pi (115200 baud)
  ==============================================================================
*/

#include <Arduino.h>

// -----------------------------------------------------------------------------
// Pin Allocations
// -----------------------------------------------------------------------------
// Motor Driver Pins (HW-095 / L298N)
#define PIN_IN1 18   // Left Forward
#define PIN_IN2 19   // Left Reverse
#define PIN_IN3 22   // Right Forward
#define PIN_IN4 23   // Right Reverse

// Front HC-SR04 Ultrasonic Sensor
#define PIN_TRIG 5   // Trigger output
#define PIN_ECHO 34  // Echo input (ADC1 / Input-only pin)

// Camera Tilt Servo Pin
#define PIN_SERVO 13 // 50 Hz PWM Servo output

// -----------------------------------------------------------------------------
// Configuration & Constants
// -----------------------------------------------------------------------------
#define PWM_FREQ 20000        // 20 kHz ultrasonic PWM frequency for silent motors
#define PWM_RES 8             // 8-bit resolution (0 - 255)
#define PWM_CH_IN1 0
#define PWM_CH_IN2 1
#define PWM_CH_IN3 2
#define PWM_CH_IN4 3

#define SERVO_PWM_FREQ 50     // 50 Hz for standard analog servo
#define SERVO_PWM_RES 16      // 16-bit resolution for smooth servo positioning
#define SERVO_PWM_CH 4
#define SERVO_MIN_US 500      // Microseconds at -45 degrees
#define SERVO_MAX_US 2400     // Microseconds at +35 degrees
#define SERVO_CENTER_US 1450  // 0 degrees level

#define SAFE_DISTANCE_CM 15.0 // Emergency obstacle stop threshold
#define WATCHDOG_MS 1000      // Auto-stop motors if no serial ping in 1s

// -----------------------------------------------------------------------------
// Global State
// -----------------------------------------------------------------------------
volatile float current_dist_cm = 100.0;
int current_tilt_angle = 0;
String current_cmd = "STOP";
int current_speed = 0;
unsigned long last_cmd_time = 0;
unsigned long last_telemetry_time = 0;
unsigned long last_sonar_time = 0;
bool auto_avoidance_enabled = true;
bool is_avoiding = false;

// -----------------------------------------------------------------------------
// Motor Low-Level Functions
// -----------------------------------------------------------------------------
void set_motors(int left_speed, int right_speed) {
  // left_speed, right_speed in range [-255, 255]
  if (left_speed > 0) {
    ledcWrite(PWM_CH_IN1, constrain(left_speed, 0, 255));
    ledcWrite(PWM_CH_IN2, 0);
  } else if (left_speed < 0) {
    ledcWrite(PWM_CH_IN1, 0);
    ledcWrite(PWM_CH_IN2, constrain(abs(left_speed), 0, 255));
  } else {
    ledcWrite(PWM_CH_IN1, 0);
    ledcWrite(PWM_CH_IN2, 0);
  }

  if (right_speed > 0) {
    ledcWrite(PWM_CH_IN3, constrain(right_speed, 0, 255));
    ledcWrite(PWM_CH_IN4, 0);
  } else if (right_speed < 0) {
    ledcWrite(PWM_CH_IN3, 0);
    ledcWrite(PWM_CH_IN4, constrain(abs(right_speed), 0, 255));
  } else {
    ledcWrite(PWM_CH_IN3, 0);
    ledcWrite(PWM_CH_IN4, 0);
  }
}

void stop_motors() {
  set_motors(0, 0);
  current_cmd = "STOP";
  current_speed = 0;
}

// -----------------------------------------------------------------------------
// Camera Servo Tilt Functions
// -----------------------------------------------------------------------------
void set_camera_tilt(int angle) {
  // angle: -45 (look down at floor) to +35 (look up at faces)
  angle = constrain(angle, -45, 35);
  current_tilt_angle = angle;
  // Map -45 to +35 to pulse width microseconds
  long us = map(angle, -45, 35, SERVO_MIN_US, SERVO_MAX_US);
  // Calculate duty cycle for 16-bit 50 Hz (period = 20,000 us)
  uint32_t duty = (us * 65535) / 20000;
  ledcWrite(SERVO_PWM_CH, duty);
}

// -----------------------------------------------------------------------------
// Non-Blocking Ultrasonic Sensor Read
// -----------------------------------------------------------------------------
float read_ultrasonic_distance() {
  digitalWrite(PIN_TRIG, LOW);
  delayMicroseconds(2);
  digitalWrite(PIN_TRIG, HIGH);
  delayMicroseconds(10);
  digitalWrite(PIN_TRIG, LOW);

  // Measure pulse with 15ms timeout (~2.5 meters max range)
  unsigned long duration = pulseIn(PIN_ECHO, HIGH, 15000);
  if (duration == 0) {
    return 150.0; // Clear path or out of range
  }
  float dist = (duration * 0.0343) / 2.0;
  return (dist > 0 && dist < 300) ? dist : 150.0;
}

// -----------------------------------------------------------------------------
// Obstacle Auto-Avoidance Reflex
// -----------------------------------------------------------------------------
void perform_auto_avoidance() {
  is_avoiding = true;
  stop_motors();
  Serial.println("{\"event\":\"OBSTACLE_AVOID\",\"action\":\"STOP\"}");
  delay(100);

  // Step 1: Backup 10 cm (Reverse at speed 120 for 300ms)
  set_motors(-120, -120);
  delay(300);

  // Step 2: Turn 45 degrees left (Turn at speed 140 for 350ms)
  set_motors(-140, 140);
  delay(350);

  // Step 3: Stop and resume normal control
  stop_motors();
  is_avoiding = false;
  Serial.println("{\"event\":\"OBSTACLE_AVOID\",\"action\":\"CLEAR\"}");
}

// -----------------------------------------------------------------------------
// Serial Command Dispatcher
// -----------------------------------------------------------------------------
void parse_command(String line) {
  line.trim();
  if (line.length() == 0) return;

  // JSON format check
  if (line.startsWith("{")) {
    // Basic JSON extraction without heavy ArduinoJson library
    int cmd_idx = line.indexOf("\"cmd\":");
    int tilt_idx = line.indexOf("\"tilt\":");
    if (tilt_idx != -1) {
      int t_val = line.substring(tilt_idx + 7).toInt();
      set_camera_tilt(t_val);
    }
    if (cmd_idx != -1) {
      int quote_start = line.indexOf("\"", cmd_idx + 6);
      int quote_end = line.indexOf("\"", quote_start + 1);
      if (quote_start != -1 && quote_end != -1) {
        String c = line.substring(quote_start + 1, quote_end);
        int spd = 60;
        int spd_idx = line.indexOf("\"speed\":");
        if (spd_idx != -1) {
          spd = line.substring(spd_idx + 8).toInt();
        }
        execute_motion(c, spd);
      }
    }
    return;
  }

  // Text format: "FWD 70", "BWD 50", "LEFT 60", "RIGHT 60", "STOP", "TILT -20"
  int space_idx = line.indexOf(' ');
  String action = (space_idx != -1) ? line.substring(0, space_idx) : line;
  int param = (space_idx != -1) ? line.substring(space_idx + 1).toInt() : 0;
  action.toUpperCase();

  if (action == "TILT") {
    set_camera_tilt(param);
  } else {
    execute_motion(action, param);
  }
}

void execute_motion(String action, int speed) {
  last_cmd_time = millis();
  int pwm_val = map(constrain(speed, 0, 100), 0, 100, 0, 255);

  if (action == "FWD") {
    if (current_dist_cm < SAFE_DISTANCE_CM && auto_avoidance_enabled) {
      perform_auto_avoidance();
      return;
    }
    set_motors(pwm_val, pwm_val);
  } else if (action == "BWD" || action == "BACK") {
    set_motors(-pwm_val, -pwm_val);
  } else if (action == "LEFT") {
    set_motors(-pwm_val, pwm_val);
  } else if (action == "RIGHT") {
    set_motors(pwm_val, -pwm_val);
  } else {
    stop_motors();
  }

  current_cmd = action;
  current_speed = speed;
}

// -----------------------------------------------------------------------------
// Arduino Setup & Main Loop
// -----------------------------------------------------------------------------
void setup() {
  Serial.begin(115200);
  Serial.setTimeout(10);

  // Setup Ultrasonic Pins
  pinMode(PIN_TRIG, OUTPUT);
  pinMode(PIN_ECHO, INPUT);

  // Setup Motor PWM Channels
  ledcSetup(PWM_CH_IN1, PWM_FREQ, PWM_RES);
  ledcSetup(PWM_CH_IN2, PWM_FREQ, PWM_RES);
  ledcSetup(PWM_CH_IN3, PWM_FREQ, PWM_RES);
  ledcSetup(PWM_CH_IN4, PWM_FREQ, PWM_RES);

  ledcAttachPin(PIN_IN1, PWM_CH_IN1);
  ledcAttachPin(PIN_IN2, PWM_CH_IN2);
  ledcAttachPin(PIN_IN3, PWM_CH_IN3);
  ledcAttachPin(PIN_IN4, PWM_CH_IN4);

  // Setup Servo PWM Channel
  ledcSetup(SERVO_PWM_CH, SERVO_PWM_FREQ, SERVO_PWM_RES);
  ledcAttachPin(PIN_SERVO, SERVO_PWM_CH);

  // Initialize Safe State
  stop_motors();
  set_camera_tilt(0); // Look level forward

  Serial.println("{\"status\":\"TARS_ESP32_READY\",\"version\":\"2.0\"}");
  last_cmd_time = millis();
}

void loop() {
  unsigned long now = millis();

  // 1. Check Serial Incoming Commands
  if (Serial.available()) {
    String incoming = Serial.readStringUntil('\n');
    parse_command(incoming);
  }

  // 2. Measure Ultrasonic Distance every 50ms
  if (now - last_sonar_time >= 50) {
    last_sonar_time = now;
    current_dist_cm = read_ultrasonic_distance();

    // Reflex Safety: If moving forward and obstacle suddenly appears < 15cm
    if (!is_avoiding && current_cmd == "FWD" && current_dist_cm < SAFE_DISTANCE_CM) {
      if (auto_avoidance_enabled) {
        perform_auto_avoidance();
      } else {
        stop_motors();
      }
    }
  }

  // 3. Safety Watchdog: Auto-halt if no serial command received in 1s while moving
  if (current_cmd != "STOP" && (now - last_cmd_time > WATCHDOG_MS)) {
    stop_motors();
    Serial.println("{\"event\":\"WATCHDOG_TIMEOUT\",\"action\":\"STOP\"}");
  }

  // 4. Emit 20 Hz Telemetry back to Raspberry Pi
  if (now - last_telemetry_time >= 50) {
    last_telemetry_time = now;
    Serial.print("{\"dist_cm\":");
    Serial.print(current_dist_cm, 1);
    Serial.print(",\"tilt\":");
    Serial.print(current_tilt_angle);
    Serial.print(",\"cmd\":\"");
    Serial.print(current_cmd);
    Serial.println("\"}");
  }
}
