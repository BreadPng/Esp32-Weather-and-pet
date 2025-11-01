"""Rotary encoder handling using micropython-rotary library (ESP32 PCNT hardware).

This is an alternative to the polling-based rotary_encoder.py implementation.
Uses ESP32's hardware pulse counter for reliable, low-CPU rotation tracking.

Install: mip.install("github:miketeachman/micropython-rotary")
Or copy rotary_irq_esp.py to your device.
"""

from machine import Pin
try:
    from rotary_irq_esp import RotaryIRQ
except ImportError:
    print("ERROR: rotary_irq_esp not found!")
    print("Install with: mip.install('github:miketeachman/micropython-rotary')")
    raise


class RotaryEncoderIRQ:
    """Wrapper around RotaryIRQ to match the RotaryEncoder API."""
    
    def __init__(
        self,
        pin_a_id,
        pin_b_id,
        button_pin_id,
        step_debounce_ms=1,  # Not used with hardware PCNT, kept for API compat
        button_debounce_ms=35,
        delta_cap=1,
    ):
        """Initialize rotary encoder with ESP32 hardware counter.
        
        Args:
            pin_a_id: GPIO for encoder A (CLK)
            pin_b_id: GPIO for encoder B (DT)
            button_pin_id: GPIO for encoder button
            step_debounce_ms: Ignored (hardware handles debouncing)
            button_debounce_ms: Software debounce for button in ms
            delta_cap: Maximum delta to return per read() call
        """
        # Initialize hardware-based rotary encoder
        self.rotary = RotaryIRQ(
            pin_num_clk=pin_a_id,
            pin_num_dt=pin_b_id,
            min_val=0,  
            max_val=1000000, 
            reverse=False,
            range_mode=RotaryIRQ.RANGE_UNBOUNDED,
            pull_up=True,
        )
        
        # Button handling (software-based with IRQ)
        self.button = Pin(button_pin_id, Pin.IN, Pin.PULL_UP)
        self._button_debounce_ms = button_debounce_ms
        self._delta_cap = delta_cap
        
        # Button state tracking
        self._button_clicked = False
        self._last_button_value = self.button.value()
        self._button_press_time = None
        
        # Attach button interrupt
        self.button.irq(trigger=Pin.IRQ_FALLING | Pin.IRQ_RISING, handler=self._button_handler)
        
        # Track last rotary value for delta calculation
        # Initialize to current value, defaulting to 0 if None
        initial_value = self.rotary.value()
        self._last_value = initial_value if initial_value is not None else 0
        
        print("RotaryEncoderIRQ initialized (ESP32 PCNT hardware)")
    
    def _button_handler(self, pin):
        """IRQ handler for button press/release."""
        import time
        current = pin.value()
        now = time.ticks_ms()
        
        if current == 0:  # Button pressed (active low)
            self._button_press_time = now
        else:  # Button released
            if self._button_press_time is not None:
                # Check debounce time
                if time.ticks_diff(now, self._button_press_time) >= self._button_debounce_ms:
                    self._button_clicked = True
                self._button_press_time = None
    
    def update(self):
        """No-op for API compatibility. Hardware handles updates automatically."""
        pass
    
    def read(self):
        """Return accumulated (delta_steps, button_clicked) since last read.
        
        Returns:
            tuple: (delta, clicked) where delta is capped to ±delta_cap
        """
        # Get current rotary value and calculate delta
        current_value = self.rotary.value()
        
        # Handle None values gracefully
        if current_value is None:
            current_value = 0
        if self._last_value is None:
            self._last_value = 0
            
        delta = current_value - self._last_value
        self._last_value = current_value
        
        # Cap delta to prevent rapid scrolling
        if delta > self._delta_cap:
            delta = self._delta_cap
        elif delta < -self._delta_cap:
            delta = -self._delta_cap
        
        # Get button state and clear it
        clicked = self._button_clicked
        self._button_clicked = False
        
        return delta, clicked
    
    def reset(self):
        """Clear any pending events and reset tracking."""
        self.rotary.reset()
        self._last_value = 0
        self._button_clicked = False
        self._button_press_time = None


def encoder_polling_loop(encoder, poll_frequency_hz=1000):
    """Polling loop for API compatibility with rotary_encoder.py.
    
    Note: With hardware PCNT, this is much less critical. The hardware
    tracks pulses automatically. We just need occasional reads.
    
    Args:
        encoder: RotaryEncoderIRQ instance
        poll_frequency_hz: Polling frequency (default 1000Hz)
    """
    import time
    poll_interval_ms = int(1000 / poll_frequency_hz)
    print("Encoder polling thread started (hardware PCNT mode) - %dHz" % poll_frequency_hz)
    while True:
        encoder.update()  # No-op, but keeps API compatible
        time.sleep_ms(poll_interval_ms)

