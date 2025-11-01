"""Perfect Timing Mini Game - Stop at exactly 10 seconds!"""

import time


GAME_NAME = "Perfect 10"


def _center_text(text, screen_width=128, char_width=8):
    """Center text horizontally on screen."""
    return max(0, (screen_width - len(text) * char_width) // 2)


def main_loop(oled, encoder):
    """Run the perfect timing mini game.
    
    Timer counts up from 0.000 to show seconds with 3 decimal places (ms).
    Player must click when it hits exactly 10.000 seconds.
    Score is based on how close they are to 10.000.
    """
    # Clear any pending input before starting
    try:
        if encoder is not None:
            encoder.reset()
    except AttributeError:
        pass
    
    # Show instructions
    oled.fill(0)
    oled.text("Stop at", _center_text("Stop at"), 10, 1)
    oled.text("10.000", _center_text("10.000"), 25, 1)
    oled.text("seconds!", _center_text("seconds!"), 40, 1)
    oled.show()
    time.sleep_ms(2000)
    
    # Countdown before starting
    # for countdown in [3, 2, 1]:
    #     oled.fill(0)
    #     countdown_text = str(countdown)
    #     oled.text(countdown_text, _center_text(countdown_text), 28, 1)
    #     oled.show()
    #     time.sleep_ms(800)
    
    # Clear encoder before starting timer
    if encoder is not None:
        encoder.reset()
    
    # Start timer
    start_time = time.ticks_ms()
    button_pressed = False
    stopped_time_ms = 0
    
    # Main timing loop
    while not button_pressed:
        now = time.ticks_ms()
        elapsed_ms = time.ticks_diff(now, start_time)
        
        # Auto-stop if they go way over (15 seconds)
        if elapsed_ms > 15000:
            stopped_time_ms = elapsed_ms
            button_pressed = True
            break
        
        # Check for button press (detect press down, not release)
        if encoder is not None:
            # Check if button is currently pressed (active low - 0 = pressed)
            if encoder.button.value() == 0:
                stopped_time_ms = elapsed_ms
                button_pressed = True
        
        # Display current time
        oled.fill(0)
        
        # Convert to seconds with 3 decimal places
        seconds = elapsed_ms / 1000.0
        
        # Format as X.XXX (with 3 decimal places)
        # MicroPython doesn't have great float formatting, so we'll do it manually
        whole_seconds = int(seconds)
        fractional = int((seconds - whole_seconds) * 1000)
        
        time_text = "%d.%03d" % (whole_seconds, fractional)
        
        # Display the timer large in center
        oled.text(time_text, _center_text(time_text), 20, 1)
        oled.text("seconds", _center_text("seconds"), 35, 1)
        oled.text("Click to stop!", _center_text("Click to stop!"), 50, 1)
        oled.show()
        
        time.sleep_ms(10)  # Small delay for responsiveness
    
    # Calculate score
    target_ms = 10000  # 10.000 seconds
    difference_ms = abs(stopped_time_ms - target_ms)
    
    # Calculate score based on accuracy
    # Perfect = 0ms off
    # 1-9ms off = very close (3 decimal places correct in tenths)
    # 10-99ms off = close (2 decimal places correct)
    # 100-999ms off = okay (1 decimal place correct)
    # 1000+ ms off = way off (0 decimal places correct)
    
    if difference_ms == 0:
        score_text = "PERFECT!!!"
        accuracy = "0.000s off"
    elif difference_ms < 10:
        score_text = "Amazing!"
        accuracy = "0.00%ds off" % difference_ms
    elif difference_ms < 100:
        score_text = "Great!"
        accuracy = "0.0%02ds off" % difference_ms
    elif difference_ms < 1000:
        score_text = "Good"
        accuracy = "0.%03ds off" % difference_ms
    else:
        score_text = "Try again"
        seconds_off = difference_ms / 1000.0
        accuracy = "%.2fs off" % seconds_off
    
    # Display result
    oled.fill(0)
    
    # Show their time
    final_seconds = stopped_time_ms / 1000.0
    whole = int(final_seconds)
    frac = int((final_seconds - whole) * 1000)
    your_time = "%d.%03d" % (whole, frac)
    
    oled.text("Your time:", _center_text("Your time:"), 5, 1)
    oled.text(your_time, _center_text(your_time), 18, 1)
    oled.text(score_text, _center_text(score_text), 35, 1)
    oled.text(accuracy, _center_text(accuracy), 48, 1)
    oled.show()
    
    # Wait before returning to menu
    time.sleep_ms(4000)
    
    # Game finished, return to main menu
    return


