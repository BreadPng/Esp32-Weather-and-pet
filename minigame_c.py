"""Spin Speed Mini Game - Spin the wheel as fast as you can!"""

import time

GAME_NAME = "Spin"


def _center_text(text, screen_width=128, char_width=8):
    """Center text horizontally on screen."""
    return max(0, (screen_width - len(text) * char_width) // 2)


def main_loop(oled, encoder):
    """Spin as fast as possible. Measures peak RPM over a rolling 1s window."""
    # Configuration
    GAME_DURATION_MS = 6000     # Total run time
    WINDOW_MS = 1000            # Sliding window for RPM calculation
    STEPS_PER_REV = 20          # Typical detents per revolution (adjust if needed)
    FRAME_DELAY_MS = 20         # UI refresh cadence

    # Prepare input and temporarily lift delta cap to capture fast spins
    original_cap = None
    try:
        if encoder is not None:
            try:
                encoder.reset()
            except AttributeError:
                pass
            original_cap = getattr(encoder, "_delta_cap", None)
            try:
                if original_cap is not None:
                    encoder._delta_cap = 1000  # allow burst reads
            except Exception:
                pass
    except Exception:
        pass

    # Intro screen
    oled.fill(0)
    oled.text("Spin the wheel!", _center_text("Spin the wheel!"), 8, 1)
    oled.text("Fast as you can", _center_text("Fast as you can"), 22, 1)
    oled.text("Click to finish", _center_text("Click to finish"), 42, 1)
    oled.show()
    time.sleep_ms(900)

    # Game state
    start_ms = time.ticks_ms()
    last_ui_ms = start_ms
    timestamps = []  # step timestamps within WINDOW_MS
    total_steps = 0
    max_rpm = 0

    # Main loop
    while True:
        now = time.ticks_ms()
        elapsed = time.ticks_diff(now, start_ms)
        if elapsed >= GAME_DURATION_MS:
            break

        # Read encoder
        clicked = False
        if encoder is not None:
            delta, clicked = encoder.read()
            if delta:
                steps = abs(int(delta))
                total_steps += steps
                for _ in range(steps):
                    timestamps.append(now)

        # End early if clicked
        if clicked:
            break

        # Drop old timestamps outside the window
        cutoff = now - WINDOW_MS
        # Efficient in-place prune for small lists
        while timestamps and timestamps[0] < cutoff:
            timestamps.pop(0)

        # Compute RPM from steps in the last window
        steps_in_window = len(timestamps)
        # rpm = steps_per_sec / steps_per_rev * 60
        rpm = (steps_in_window * 60000) // (STEPS_PER_REV * WINDOW_MS) if STEPS_PER_REV > 0 else 0
        if rpm > max_rpm:
            max_rpm = rpm

        # UI update at cadence
        if time.ticks_diff(now, last_ui_ms) >= FRAME_DELAY_MS:
            remaining = max(0, (GAME_DURATION_MS - elapsed) // 1000)
            oled.fill(0)
            oled.text("SPIN!", _center_text("SPIN!"), 0, 1)
            oled.text("Time: %ds" % remaining, 2, 14, 1)
            oled.text("RPM:", 2, 30, 1)
            # Right-align current rpm
            rpm_text = "%4d" % rpm
            oled.text(rpm_text, 128 - (len(rpm_text) * 8) - 2, 30, 1)
            oled.text("Max:", 2, 44, 1)
            max_text = "%4d" % max_rpm
            oled.text(max_text, 128 - (len(max_text) * 8) - 2, 44, 1)
            oled.show()
            last_ui_ms = now

        time.sleep_ms(FRAME_DELAY_MS)

    # Final results
    total_revs_int = total_steps // STEPS_PER_REV if STEPS_PER_REV > 0 else 0
    oled.fill(0)
    oled.text("RESULT", _center_text("RESULT"), 4, 1)
    oled.text("Max RPM:", 8, 22, 1)
    oled.text("%d" % max_rpm, _center_text("%d" % max_rpm), 36, 1)
    oled.text("%d revs" % total_revs_int, _center_text("%d revs" % total_revs_int), 50, 1)
    oled.show()
    time.sleep_ms(2500)

    # Restore encoder state
    try:
        if encoder is not None:
            if original_cap is not None:
                try:
                    encoder._delta_cap = original_cap
                except Exception:
                    pass
            try:
                encoder.reset()
            except AttributeError:
                pass
    except Exception:
        pass

    return


