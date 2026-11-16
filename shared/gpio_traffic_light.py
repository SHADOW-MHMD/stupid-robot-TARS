"""
TARS Hardware UI: 3-LED Traffic Light Controller (shared/gpio_traffic_light.py).

Controls physical LEDs on the Raspberry Pi GPIO header using gpiozero (LED, PWMLED).
Provides seamless MockLED fallback for non-Pi / test / CI environments when gpiozero
pin factories or physical GPIO devices are unavailable.

Physical Wiring Pinout Specification for Raspberry Pi 40-Pin Header:
====================================================================
- 🟢 Green LED (Listening / Mic Hot):
    - Anode (+) -> 220Ω / 330Ω Resistor -> BCM GPIO 17 (Physical Pin 11)
    - Cathode (-) -> Ground (Physical Pin 9 or Pin 6)
- 🟡 Yellow LED (Thinking / Processing / Wandering):
    - Anode (+) -> 220Ω / 330Ω Resistor -> BCM GPIO 27 (Physical Pin 13)
    - Cathode (-) -> Ground (Physical Pin 14)
- 🔴 Red LED (Speaking / Muted / Inauguration / Failsafe Error):
    - Anode (+) -> 220Ω / 330Ω Resistor -> BCM GPIO 22 (Physical Pin 15)
    - Cathode (-) -> Ground (Physical Pin 20 or Pin 25)

State Mapping Matrix:
=====================
| System State     | Green (GPIO 17) | Yellow (GPIO 27)    | Red (GPIO 22)       |
|------------------|-----------------|----------------------|---------------------|
| `LISTENING`      | ON              | OFF                  | OFF                 |
| `THINKING`       | OFF             | ON                   | OFF                 |
| `WANDERING`      | OFF             | PULSE (1 Hz PWM)     | OFF                 |
| `SPEAKING`       | OFF             | OFF                  | ON                  |
| `MUTED`          | OFF             | OFF                  | ON                  |
| `INAUGURATION`   | OFF             | OFF                  | ON                  |
| `FAILSAFE_ERROR` | OFF             | OFF                  | BLINK (5 Hz: 0.1s)  |
| `IDLE`           | OFF             | OFF                  | OFF                 |
"""

from __future__ import annotations

from enum import Enum
import logging
import threading
import time
from typing import Any, Optional, Union

logger = logging.getLogger("TARS.HardwareUI.TrafficLight")

# Attempt real gpiozero import
GPIOZERO_AVAILABLE = False
try:
    import warnings
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore")
        from gpiozero import LED, PWMLED
        from gpiozero.exc import BadPinFactory, GPIOZeroError
    GPIOZERO_AVAILABLE = True
except (ImportError, Exception) as exc:
    logger.debug(f"gpiozero not available or failed import: {exc}")
    GPIOZERO_AVAILABLE = False


class MockLED:
    """
    Mock LED device for test and dev environments without physical GPIO hardware.
    """

    def __init__(self, pin: int):
        self.pin = int(pin)
        self.is_lit = False
        self.is_blinking = False
        self.is_pulsing = False
        self.value: float = 0.0
        self.blink_freq: float = 0.0
        self.closed: bool = False

    def on(self) -> None:
        """Turn on the LED (solid)."""
        self.is_lit = True
        self.is_blinking = False
        self.is_pulsing = False
        self.value = 1.0

    def off(self) -> None:
        """Turn off the LED."""
        self.is_lit = False
        self.is_blinking = False
        self.is_pulsing = False
        self.value = 0.0
        self.blink_freq = 0.0

    def blink(
        self,
        on_time: float = 0.1,
        off_time: float = 0.1,
        n: Optional[int] = None,
        background: bool = True,
    ) -> None:
        """Blink the LED at specified period."""
        self.is_lit = True
        self.is_blinking = True
        self.is_pulsing = False
        period = float(on_time) + float(off_time)
        self.blink_freq = 1.0 / period if period > 0 else 0.0
        self.value = 1.0

    def pulse(
        self,
        fade_in_time: float = 0.5,
        fade_out_time: float = 0.5,
        n: Optional[int] = None,
        background: bool = True,
    ) -> None:
        """Pulse the LED using simulated PWM fade."""
        self.is_lit = True
        self.is_blinking = True
        self.is_pulsing = True
        period = float(fade_in_time) + float(fade_out_time)
        self.blink_freq = 1.0 / period if period > 0 else 0.0
        self.value = 0.5

    def close(self) -> None:
        """Release mock resources."""
        self.off()
        self.closed = True


class TrafficLightState(str, Enum):
    """Canonical traffic light states."""
    IDLE = "IDLE"
    LISTENING = "LISTENING"
    THINKING = "THINKING"
    WANDERING = "WANDERING"
    SPEAKING = "SPEAKING"
    MUTED = "MUTED"
    INAUGURATION = "INAUGURATION"
    FAILSAFE_ERROR = "FAILSAFE_ERROR"

    def __str__(self) -> str:
        return self.value


class TrafficLightController:
    """
    Coordinates 3-LED hardware state transitions on Raspberry Pi (GPIO 17, 27, 22).
    Provides real gpiozero control with automatic MockLED fallback.
    """

    def __init__(
        self,
        green_pin: int = 17,
        yellow_pin: int = 27,
        red_pin: int = 22,
        force_mock: bool = False,
    ) -> None:
        self.green_pin = int(green_pin)
        self.yellow_pin = int(yellow_pin)
        self.red_pin = int(red_pin)
        self.force_mock = bool(force_mock)
        self.state: TrafficLightState = TrafficLightState.IDLE
        self._lock = threading.Lock()
        self.is_mock = False

        self.green_led: Union[LED, MockLED]
        self.yellow_led: Union[PWMLED, MockLED]
        self.red_led: Union[LED, MockLED]

        self._init_hardware()

    def _init_hardware(self) -> None:
        """Initializes gpiozero devices or falls back to MockLED."""
        self.is_mock = self.force_mock or not GPIOZERO_AVAILABLE

        if not self.is_mock:
            try:
                self.green_led = LED(self.green_pin)
                try:
                    self.yellow_led = PWMLED(self.yellow_pin)
                except Exception:
                    self.yellow_led = LED(self.yellow_pin)
                self.red_led = LED(self.red_pin)
                logger.info(
                    f"gpiozero TrafficLight active (Green: GPIO {self.green_pin}/Pin 11, "
                    f"Yellow: GPIO {self.yellow_pin}/Pin 13, Red: GPIO {self.red_pin}/Pin 15)"
                )
                return
            except Exception as e:
                logger.warning(
                    f"Could not initialize gpiozero devices ({e}); falling back to MockLED."
                )
                self.is_mock = True

        self.green_led = MockLED(self.green_pin)
        self.yellow_led = MockLED(self.yellow_pin)
        self.red_led = MockLED(self.red_pin)
        logger.info(
            f"Mock TrafficLight initialized (Green: {self.green_pin}, "
            f"Yellow: {self.yellow_pin}, Red: {self.red_pin})"
        )

    def set_state(self, state: Union[TrafficLightState, str]) -> None:
        """
        Transition traffic light to new operational state.
        Thread-safe.
        """
        with self._lock:
            state_str = str(state).strip().upper()
            if state_str == "ERROR" or state_str == "FAILSAFE":
                state_enum = TrafficLightState.FAILSAFE_ERROR
            elif state_str in TrafficLightState.__members__:
                state_enum = TrafficLightState[state_str]
            else:
                try:
                    state_enum = TrafficLightState(state_str)
                except ValueError:
                    logger.warning(f"Unknown traffic light state: '{state}'; defaulting to IDLE")
                    state_enum = TrafficLightState.IDLE

            self.state = state_enum

            if state_enum == TrafficLightState.LISTENING:
                self.green_led.on()
                self.yellow_led.off()
                self.red_led.off()

            elif state_enum == TrafficLightState.THINKING:
                self.green_led.off()
                self.yellow_led.on()
                self.red_led.off()

            elif state_enum == TrafficLightState.WANDERING:
                self.green_led.off()
                if hasattr(self.yellow_led, "pulse"):
                    try:
                        self.yellow_led.pulse(fade_in_time=0.5, fade_out_time=0.5)
                    except Exception:
                        self.yellow_led.blink(on_time=0.5, off_time=0.5)
                else:
                    self.yellow_led.blink(on_time=0.5, off_time=0.5)
                self.red_led.off()

            elif state_enum in (
                TrafficLightState.SPEAKING,
                TrafficLightState.MUTED,
                TrafficLightState.INAUGURATION,
            ):
                self.green_led.off()
                self.yellow_led.off()
                self.red_led.on()

            elif state_enum == TrafficLightState.FAILSAFE_ERROR:
                self.green_led.off()
                self.yellow_led.off()
                # 5 Hz rapid alert blinking (0.1s on / 0.1s off)
                self.red_led.blink(on_time=0.1, off_time=0.1)

            elif state_enum == TrafficLightState.IDLE:
                self.green_led.off()
                self.yellow_led.off()
                self.red_led.off()

            logger.debug(f"TrafficLight state set to: {self.state}")

    def get_state(self) -> TrafficLightState:
        """Returns the current traffic light state."""
        return self.state

    def strobe(self, duration_sec: float = 3.0, frequency_hz: float = 10.0) -> None:
        """
        Rapidly flashes all 3 LEDs (Green, Yellow, Red) simultaneously in a background thread.
        Restores the previous state upon completion.
        """
        def _run_strobe():
            with self._lock:
                prev_state = self.state
            period = 1.0 / max(1.0, float(frequency_hz))
            half_period = period / 2.0
            end_time = time.time() + float(duration_sec)
            try:
                while time.time() < end_time:
                    try:
                        self.green_led.on()
                        self.yellow_led.on()
                        self.red_led.on()
                    except Exception:
                        pass
                    time.sleep(half_period)
                    try:
                        self.green_led.off()
                        self.yellow_led.off()
                        self.red_led.off()
                    except Exception:
                        pass
                    time.sleep(half_period)
            finally:
                self.set_state(prev_state)

        thread = threading.Thread(target=_run_strobe, daemon=True, name="TARS-LED-Strobe")
        thread.start()

    def close(self) -> None:
        """Release LED hardware/mock resources."""
        with self._lock:
            try:
                self.green_led.close()
            except Exception:
                pass
            try:
                self.yellow_led.close()
            except Exception:
                pass
            try:
                self.red_led.close()
            except Exception:
                pass
            self.state = TrafficLightState.IDLE
            logger.info("TrafficLight controller closed.")
