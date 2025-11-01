"""Reaction Time Mini Game - Test your reflexes!"""

import time
import random


GAME_NAME = "Reaction Time"


def _center_text(text, screen_width=128, char_width=8):
    """Center text horizontally on screen."""
    return max(0, (screen_width - len(text) * char_width) // 2)


def main_loop(oled, encoder):
    """Run the reaction time mini game.
    
    Screen flashes white for one frame, player presses button as fast as possible.
    Displays reaction time in milliseconds. Runs 5 rounds total.
    """
    # Clear any pending input before starting
    try:
        if encoder is not None:
            encoder.reset()
    except AttributeError:
        pass
    
    rounds = 5
    reaction_times = []
    
    for round_num in range(1, rounds + 1):
        # Show "Ready..." message
        oled.fill(0)
        ready_text = "Round %d/%d" % (round_num, rounds)
        oled.text(ready_text, _center_text(ready_text), 20, 1)
        oled.text("Get Ready...", _center_text("Get Ready..."), 35, 1)
        oled.show()
        
        # Wait random time (1-3 seconds) to prevent anticipation
        wait_time = random.randint(1000, 3000)
        time.sleep_ms(wait_time)
        
        # Clear any button presses that happened during wait
        if encoder is not None:
            encoder.reset()
        
        # FLASH! - Fill screen white for one frame
        
        oled.fill(1)
        oled.show()
        oled.fill(0)
        oled.show()
        
        # Start timing immediately after flash
        start_time = time.ticks_ms()
        
        # Wait for button press
        button_pressed = False
        timeout_ms = 5000  # 5 second timeout
        
        while not button_pressed:
            now = time.ticks_ms()
            
            # Check for timeout
            if time.ticks_diff(now, start_time) > timeout_ms:
                reaction_time = -1  # Indicate timeout
                break
            
            # Check for button press
            if encoder is not None:
                delta, clicked = encoder.read()
                if clicked:
                    reaction_time = time.ticks_diff(now, start_time)
                    button_pressed = True
            
            time.sleep_ms(5)  
        
        # Store result
        if reaction_time > 0:
            reaction_times.append(reaction_time)
        
        # Display result for this round
        oled.fill(0)
        if reaction_time > 0:
            result_text = "%d ms" % reaction_time
            oled.text("Reaction Time:", _center_text("Reaction Time:"), 20, 1)
            oled.text(result_text, _center_text(result_text), 35, 1)
        else:
            oled.text("Too Slow!", _center_text("Too Slow!"), 28, 1)
        oled.show()
        
        # Pause to show result
        time.sleep_ms(1500)
        
        # Clear encoder for next round
        if encoder is not None:
            encoder.reset()
    
    # Show final results - calculate average
    oled.fill(0)
    if reaction_times:
        avg_time = sum(reaction_times) // len(reaction_times)
        oled.text("Average Time:", _center_text("Average Time:"), 15, 1)
        avg_text = "%d ms" % avg_time
        oled.text(avg_text, _center_text(avg_text), 30, 1)
        
        # Show performance rating
        if avg_time < 200:
            rating = "DAMN GIRL!"
        elif avg_time < 300:
            rating = "WOAH!"
        elif avg_time < 400:
            rating = "Good!"
        else:
            rating = "Keep trying..."
        oled.text(rating, _center_text(rating), 45, 1)
    else:
        oled.text("No valid times", _center_text("No valid times"), 28, 1)
    
    oled.show()
    time.sleep_ms(2500)
    
    # Game finished, return to main menu
    return


