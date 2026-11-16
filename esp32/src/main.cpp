/*
  ==============================================================================
  TARS 4WD Autonomous Robot — ESP32 Actuation Firmware
  Board: ESP32 38-Pin DevKit (ESP-WROOM-32)
  Hardware:
    - HW-095 (L298N) 4WD H-Bridge Motor Driver (IN1: 18, IN2: 19, IN3: 22, IN4: 23)
    - Front Ultrasonic HC-SR04 Sensor (Trig: 5, Echo: 34)
    - Camera Tilt Micro-Servo (GPIO 13, 12, 14, 15, 2, 4 via FreeRTOS 50Hz task)
    - Serial Bridge (115200 baud, 20 Hz JSON Telemetry + Motor/Tilt Commands)
  ==============================================================================
*/

#include <Arduino.h>

// -----------------------------------------------------------------------------
// Pin Allocations for 38-Pin ESP32
// -----------------------------------------------------------------------------
#define PIN_IN1 18   // Motor Left Forward
#define PIN_IN2 19   // Motor Left Reverse
#define PIN_IN3 22   // Motor Right Forward
#define PIN_IN4 23   // Motor Right Reverse

#define PIN_TRIG 5   // Ultrasonic Trigger
#define PIN_ECHO 34  // Ultrasonic Echo (Input-only ADC1 pin)

#define PIN_SERVO 13 // Camera Tilt Servo

const int SERVO_PINS[] = {13, 12, 14, 15, 2, 4};
const int NUM_SERVO_PINS = sizeof(SERVO_PINS) / sizeof(SERVO_PINS[0]);

// -----------------------------------------------------------------------------
// Constants & Configuration
// -----------------------------------------------------------------------------
#define PWM_FREQ 20000        // 20 kHz ultrasonic PWM for silent motors
#define PWM_RES 8             // 8-bit resolution (0 - 255)
#define PWM_CH_IN1 0
#define PWM_CH_IN2 1
#define PWM_CH_IN3 2
#define PWM_CH_IN4 3

#define SAFE_DISTANCE_CM 15.0 // Emergency obstacle stop threshold
#define WATCHDOG_MS 1000      // Auto-stop motors if no serial ping in 1s

// -----------------------------------------------------------------------------
// Global State
// -----------------------------------------------------------------------------
volatile float current_dist_cm = 100.0;
volatile int current_tilt_angle = 0;
volatile int current_servo_us = 1500; // 1500us = Level Horizon (0°)

String current_cmd = "STOP";
int current_speed = 0;
unsigned long last_cmd_time = 0;
unsigned long last_telemetry_time = 0;
unsigned long last_sonar_time = 0;
bool auto_avoidance_enabled = true;
bool is_avoiding = false;

// -----------------------------------------------------------------------------
// FreeRTOS Background Task: 50 Hz Servo Pulse Generator
// -----------------------------------------------------------------------------
void servo_pulse_task(void *pvParameters) {
  for (;;) {
    int us = current_servo_us;
    for (int i = 0; i < NUM_SERVO_PINS; i++) {
      digitalWrite(SERVO_PINS[i], HIGH);
    }
    delayMicroseconds(us);
    for (int i = 0; i < NUM_SERVO_PINS; i++) {
      digitalWrite(SERVO_PINS[i], LOW);
    }
    vTaskDelay(pdMS_TO_TICKS(20)); // Exactly 20 ms (50 Hz frame)
  }
}

// -----------------------------------------------------------------------------
// Low-Level Motor PWM Helper
// -----------------------------------------------------------------------------
void pwm_write(uint8_t pin, uint8_t channel, uint32_t duty) {
#if defined(ESP_ARDUINO_VERSION_MAJOR) && (ESP_ARDUINO_VERSION_MAJOR >= 3)
  ledcWrite(pin, duty);
#else
  ledcWrite(channel, duty);
#endif
}

// Forward Declarations
void stop_motors();
void set_motors(int left_speed, int right_speed);
void execute_motion(String action, int speed);
void set_camera_tilt(int angle);
float read_ultrasonic_distance();
void perform_auto_avoidance();
void parse_command(String line);

// -----------------------------------------------------------------------------
// Motor Control (HW-095 / L298N H-Bridge)
// -----------------------------------------------------------------------------
void set_motors(int left_speed, int right_speed) {
  if (left_speed > 0) {
    pwm_write(PIN_IN1, PWM_CH_IN1, constrain(left_speed, 0, 255));
    pwm_write(PIN_IN2, PWM_CH_IN2, 0);
  } else if (left_speed < 0) {
    pwm_write(PIN_IN1, PWM_CH_IN1, 0);
    pwm_write(PIN_IN2, PWM_CH_IN2, constrain(abs(left_speed), 0, 255));
  } else {
    pwm_write(PIN_IN1, PWM_CH_IN1, 0);
    pwm_write(PIN_IN2, PWM_CH_IN2, 0);
  }

  if (right_speed > 0) {
    pwm_write(PIN_IN3, PWM_CH_IN3, constrain(right_speed, 0, 255));
    pwm_write(PIN_IN4, PWM_CH_IN4, 0);
  } else if (right_speed < 0) {
    pwm_write(PIN_IN3, PWM_CH_IN3, 0);
    pwm_write(PIN_IN4, PWM_CH_IN4, constrain(abs(right_speed), 0, 255));
  } else {
    pwm_write(PIN_IN3, PWM_CH_IN3, 0);
    pwm_write(PIN_IN4, PWM_CH_IN4, 0);
  }
}

void stop_motors() {
  set_motors(0, 0);
  current_cmd = "STOP";
  current_speed = 0;
}

// -----------------------------------------------------------------------------
// Camera Tilt Servo
// -----------------------------------------------------------------------------
void set_camera_tilt(int angle) {
  angle = constrain(angle, -45, 45);
  current_tilt_angle = angle;
  // -45° (Floor) = 1000us, 0° (Center) = 1500us, +45° (Faces) = 2000us
  current_servo_us = map(angle, -45, 45, 1000, 2000);
}

// -----------------------------------------------------------------------------
// Ultrasonic Sensor Reading (HC-SR04)
// -----------------------------------------------------------------------------
float read_ultrasonic_distance() {
  digitalWrite(PIN_TRIG, LOW);
  delayMicroseconds(2);
  digitalWrite(PIN_TRIG, HIGH);
  delayMicroseconds(10);
  digitalWrite(PIN_TRIG, LOW);

  unsigned long duration = pulseIn(PIN_ECHO, HIGH, 25000); // 25ms timeout (~4m max)
  if (duration == 0) {
    return 150.0;
  }
  float dist = (duration * 0.0343) / 2.0;
  return (dist > 0 && dist < 350) ? dist : 150.0;
}

// -----------------------------------------------------------------------------
// Obstacle Auto-Avoidance Reflex
// -----------------------------------------------------------------------------
void perform_auto_avoidance() {
  is_avoiding = true;
  stop_motors();
  Serial.println("{\"event\":\"OBSTACLE_AVOID\",\"action\":\"STOP\"}");
  delay(100);

  // Step 1: Reverse at speed 140 for 300ms
  set_motors(-140, -140);
  delay(300);

  // Step 2: Pivot Left at speed 150 for 350ms
  set_motors(-150, 150);
  delay(350);

  stop_motors();
  is_avoiding = false;
  Serial.println("{\"event\":\"OBSTACLE_AVOID\",\"action\":\"CLEAR\"}");
}

// -----------------------------------------------------------------------------
// Serial Command Parsing
// -----------------------------------------------------------------------------
void parse_command(String line) {
  line.trim();
  if (line.length() == 0) return;

  // JSON format: {"cmd": "FWD", "speed": 60, "tilt": 15}
  if (line.startsWith("{")) {
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
  } else if (action == "STOP") {
    stop_motors();
    return;
  }
  current_cmd = action;
  current_speed = speed;
}

// -----------------------------------------------------------------------------
// Setup & Loop
// -----------------------------------------------------------------------------
void setup() {
  Serial.begin(115200);
  Serial.setTimeout(10);

  // Setup Ultrasonic Pins
  pinMode(PIN_TRIG, OUTPUT);
  pinMode(PIN_ECHO, INPUT);

  // Setup Motor Pins
#if defined(ESP_ARDUINO_VERSION_MAJOR) && (ESP_ARDUINO_VERSION_MAJOR >= 3)
  ledcAttach(PIN_IN1, PWM_FREQ, PWM_RES);
  ledcAttach(PIN_IN2, PWM_FREQ, PWM_RES);
  ledcAttach(PIN_IN3, PWM_FREQ, PWM_RES);
  ledcAttach(PIN_IN4, PWM_FREQ, PWM_RES);
#else
  ledcSetup(PWM_CH_IN1, PWM_FREQ, PWM_RES);
  ledcSetup(PWM_CH_IN2, PWM_FREQ, PWM_RES);
  ledcSetup(PWM_CH_IN3, PWM_FREQ, PWM_RES);
  ledcSetup(PWM_CH_IN4, PWM_FREQ, PWM_RES);

  ledcAttachPin(PIN_IN1, PWM_CH_IN1);
  ledcAttachPin(PIN_IN2, PWM_CH_IN2);
  ledcAttachPin(PIN_IN3, PWM_CH_IN3);
  ledcAttachPin(PIN_IN4, PWM_CH_IN4);
#endif

  // Setup Servo Pins
  for (int i = 0; i < NUM_SERVO_PINS; i++) {
    pinMode(SERVO_PINS[i], OUTPUT);
    digitalWrite(SERVO_PINS[i], LOW);
  }

  // Start FreeRTOS 50 Hz background pulse generator task on Core 1
  xTaskCreatePinnedToCore(
    servo_pulse_task,
    "servo_pulse",
    2048,
    NULL,
    1,
    NULL,
    1
  );

  stop_motors();
  set_camera_tilt(0); // Center at level horizon (1500us)

  Serial.println("{\"status\":\"TARS_ESP32_READY\",\"version\":\"2.0\"}");
  last_cmd_time = millis();
}

void loop() {
  unsigned long now = millis();

  // 1. Read Serial Commands
  if (Serial.available()) {
    String incoming = Serial.readStringUntil('\n');
    parse_command(incoming);
  }

  // 2. Measure Ultrasonic Distance every 50ms (20 Hz)
  if (now - last_sonar_time >= 50) {
    last_sonar_time = now;
    current_dist_cm = read_ultrasonic_distance();

    if (!is_avoiding && current_cmd == "FWD" && current_dist_cm < SAFE_DISTANCE_CM) {
      if (auto_avoidance_enabled) {
        perform_auto_avoidance();
      } else {
        stop_motors();
      }
    }
  }

  // 3. Safety Watchdog: auto-stop after 1s if no command while moving
  if (current_cmd != "STOP" && (now - last_cmd_time > WATCHDOG_MS)) {
    stop_motors();
    Serial.println("{\"event\":\"WATCHDOG_TIMEOUT\",\"action\":\"STOP\"}");
  }

  // 4. Emit 20 Hz Telemetry to Serial (JSON format)
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
