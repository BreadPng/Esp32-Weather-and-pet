"""Rotary encoder handling with debouncing for ESP32/MicroPython."""

from machine import Pin
import time
import _thread


class RotaryEncoder:
    """Poll-based rotary encoder reader with debounced rotation and button."""

    def __init__(
        self,
        pin_a_id,
        pin_b_id,
        button_pin_id,
        step_debounce_ms=5,
        button_debounce_ms=35,
    ):
        self.pin_a = Pin(pin_a_id, Pin.IN, Pin.PULL_UP)
        self.pin_b = Pin(pin_b_id, Pin.IN, Pin.PULL_UP)
        self.button = Pin(button_pin_id, Pin.IN, Pin.PULL_UP)

        self._step_debounce_ms = step_debounce_ms
        self._button_debounce_ms = button_debounce_ms

        # Track full encoder state (both A and B pins)
        self._last_encoded = (self.pin_a.value() << 1) | self.pin_b.value()
        self._last_button = self.button.value()

        now = time.ticks_ms()
        self._last_step_time = now
        self._last_button_time = now
        self._button_press_time = None

        # Gray code state transition lookup table
        # Format: [last_state << 2 | current_state] = direction
        # Valid transitions: 0=no change, 1=CW, -1=CCW
        self._transition_table = [
            0, -1,  1,  0,   # from 00: 00->00(0), 00->01(-1), 00->10(1), 00->11(0-invalid)
            1,  0,  0, -1,   # from 01: 01->00(1), 01->01(0), 01->10(0-invalid), 01->11(-1)
           -1,  0,  0,  1,   # from 10: 10->00(-1), 10->01(0-invalid), 10->10(0), 10->11(1)
            0,  1, -1,  0    # from 11: 11->00(0-invalid), 11->01(1), 11->10(-1), 11->11(0)
        ]

        # Thread-safe shared state
        self._lock = _thread.allocate_lock()
        self._rotation_delta = 0
        self._button_clicked = False

    def update(self):
        """Poll the encoder and button, updating internal event counters."""
        self._read_rotation()
        self._read_button()

    def _read_rotation(self):
        # Read both encoder pins and encode as 2-bit value
        current_a = self.pin_a.value()
        current_b = self.pin_b.value()
        current_encoded = (current_a << 1) | current_b
        
        # Check if state changed
        if current_encoded != self._last_encoded:
            now = time.ticks_ms()
            if time.ticks_diff(now, self._last_step_time) >= self._step_debounce_ms:
                # Use Gray code state transition table for robust direction detection
                transition = (self._last_encoded << 2) | current_encoded
                direction = self._transition_table[transition]
                
                # Only acquire lock if we have a valid rotation to record
                if direction != 0:  # Valid transition
                    self._lock.acquire()
                    self._rotation_delta += direction
                    self._lock.release()
                    self._last_step_time = now
                
                self._last_encoded = current_encoded  # Update state after debounce

    def _read_button(self):
        current_button = self.button.value()
        if current_button != self._last_button:
            now = time.ticks_ms()
            if time.ticks_diff(now, self._last_button_time) >= self._button_debounce_ms:
                self._last_button_time = now
                self._last_button = current_button  # Update after debounce
                if current_button == 0:  # Button pressed (active low)
                    self._button_press_time = now
                else:  # Button released
                    if self._button_press_time is not None:
                        self._lock.acquire()
                        self._button_clicked = True
                        self._lock.release()
                    self._button_press_time = None

    def read(self):
        """Return accumulated (delta_steps, button_clicked) since last read.
        Delta is capped to ±1 to prevent rapid scrolling.
        """
        self._lock.acquire()
        delta = self._rotation_delta
        clicked = self._button_clicked
        self._rotation_delta = 0
        self._button_clicked = False
        self._lock.release()
        
        # Cap delta to ±1 to prevent rapid scrolling
        if delta > 1:
            delta = 1
        elif delta < -1:
            delta = -1
        
        return delta, clicked

    def reset(self):
        """Clear any pending events and reset debounce tracking."""
        self._lock.acquire()
        self._rotation_delta = 0
        self._button_clicked = False
        self._lock.release()
        self._last_encoded = (self.pin_a.value() << 1) | self.pin_b.value()
        self._last_button = self.button.value()
        now = time.ticks_ms()
        self._last_step_time = now
        self._last_button_time = now
        self._button_press_time = None


def encoder_polling_loop(encoder, poll_frequency_hz=1000):
    """Dedicated polling loop for encoder - runs on separate core.
    
    Args:
        encoder: RotaryEncoder instance to poll
        poll_frequency_hz: Polling frequency in Hz (default 5000Hz = 200us interval)
                          Supports up to ~10kHz reliably with microsecond sleep
    """
    #poll_interval_us = int(1000000 / poll_frequency_hz)
    poll_interval_us = int(1000 / poll_frequency_hz)
    print("Encoder polling thread started - %dHz (%dus interval)" % (poll_frequency_hz, poll_interval_us))
    while True:
        encoder.update()
        #time.sleep_us(poll_interval_us)
        time.sleep_ms(poll_interval_us)

