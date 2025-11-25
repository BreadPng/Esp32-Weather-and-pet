from machine import Pin, I2C, RTC
import time
import network
import urequests
import ssd1306
import _thread
from menu import Menu
import minigame_a
import minigame_b
import minigame_c
from sprites import (
    PET_W, PET_H, MOOD_FRAMES,
    MOOD_HAPPY, MOOD_SAD, MOOD_BORED, MOOD_LOVE, MOOD_POUTING,
    ICON_W, ICON_H, HOUSE_ICON, SUN_ICON
)
import machine
# Import sensitive configuration from separate file
from config import (
    WIFI_SSID, WIFI_PASSWORD,
    OPENWEATHER_API_KEY, OPENWEATHER_LAT, OPENWEATHER_LON,
    TIMEZONE_OFFSET,
    USE_HARDWARE_ENCODER
)

# Import appropriate rotary encoder implementation
# Switch between implementations in config.py with USE_HARDWARE_ENCODER flag
# - False (default): rotary_encoder.py - polling-based, no dependencies
# - True: rotary_encoder_irq.py - ESP32 PCNT hardware, requires: mip.install("github:miketeachman/micropython-rotary")
time.sleep(1)
if USE_HARDWARE_ENCODER:
    try:
        print("Using hardware-based rotary encoder (ESP32 PCNT)")
        # Import directly from the library module placed on the device
        from rotary_irq_esp import RotaryIRQ
        # Adapter to match the polling encoder API (read/reset)
        class RotaryEncoder:
            def __init__(
                self,
                pin_a_id,
                pin_b_id,
                button_pin_id,
                step_debounce_ms=1,
                button_debounce_ms=35,
                delta_cap=1,
            ):
                # Hardware rotary (unbounded range)
                self.rotary = RotaryIRQ(
                    pin_num_clk=pin_a_id,
                    pin_num_dt=pin_b_id,
                    min_val=0,
                    max_val=1000000,
                    reverse=False,
                    range_mode=RotaryIRQ.RANGE_UNBOUNDED,
                    pull_up=True,
                )
                # Button (active-low)
                self.button = Pin(button_pin_id, Pin.IN, Pin.PULL_UP)
                self._button_debounce_ms = button_debounce_ms
                self._delta_cap = delta_cap
                self._button_clicked = False
                self._button_press_time = None
                # Attach IRQ for button clicks
                self.button.irq(
                    trigger=Pin.IRQ_FALLING | Pin.IRQ_RISING,
                    handler=self._button_irq,
                )
                # Track last value for delta computation
                initial_value = self.rotary.value()
                self._last_value = initial_value if initial_value is not None else 0
            
            def _button_irq(self, pin):
                import time as _t
                current = pin.value()
                now = _t.ticks_ms()
                if current == 0:
                    self._button_press_time = now
                else:
                    if self._button_press_time is not None:
                        if _t.ticks_diff(now, self._button_press_time) >= self._button_debounce_ms:
                            self._button_clicked = True
                    self._button_press_time = None
            
            def update(self):
                # Hardware counts pulses; nothing to do here
                pass
            
            def read(self):
                current_value = self.rotary.value()
                if current_value is None:
                    current_value = 0
                if self._last_value is None:
                    self._last_value = current_value
                delta = current_value - self._last_value
                self._last_value = current_value
                # Cap delta to ±delta_cap
                if delta > self._delta_cap:
                    delta = self._delta_cap
                elif delta < -self._delta_cap:
                    delta = -self._delta_cap
                clicked = self._button_clicked
                self._button_clicked = False
                return delta, clicked
            
            def reset(self):
                try:
                    # RotaryIRQ.reset() resets to min_val
                    self.rotary.reset()
                except Exception:
                    try:
                        self.rotary.set(value=0)
                    except Exception:
                        pass
                v = self.rotary.value()
                self._last_value = v if v is not None else 0
                self._button_clicked = False
                self._button_press_time = None
        
        # Provide a no-op polling loop for API compatibility
        def encoder_polling_loop(encoder, poll_frequency_hz=1000):
            import time
            poll_interval_ms = int(1000 / poll_frequency_hz)
            print("Encoder polling thread started (hardware PCNT mode) - %dHz" % poll_frequency_hz)
            while True:
                time.sleep_ms(poll_interval_ms)
    except ImportError as e:
        print("WARNING: Hardware encoder library not found!")
        print("Install with: mip.install('github:miketeachman/micropython-rotary')")
        print("Falling back to polling encoder...")
        from rotary_encoder import RotaryEncoder, encoder_polling_loop
else:
    print("Using polling-based rotary encoder")
    from rotary_encoder import RotaryEncoder, encoder_polling_loop

# ========== CONFIGURATION ==========

# I2C pins
I2C_SDA = 21
I2C_SCL = 22

# Rotary encoder pins (GPIO numbers)
# Use GPIO18/19 for A/B to avoid bootstrapping pins; button on GPIO23.
ROTARY_PIN_A = 18
ROTARY_PIN_B = 19
ROTARY_BUTTON_PIN = 23

# Menu timings (milliseconds)
MENU_IDLE_TIMEOUT_MS = 6000
ACTION_VIEW_DURATION_MS = 3000
MENU_VISIBLE_COUNT = 3

# Timing
FRAME_TIME = 800  # ms per animation frame
TARGET_FPS = 15  # Display refresh target
RENDER_INTERVAL_MS = (1000 + TARGET_FPS - 1) // TARGET_FPS  # Ceiling division to cap FPS
SENSOR_UPDATE_INTERVAL_MS = 2000  # How often to refresh indoor sensor readings
MOOD_CHANGE_INTERVAL = 5 * 60 * 1000  # 5 minutes in ms
WEATHER_UPDATE_INTERVAL = 10 * 60 * 1000  # 10 minutes in ms

# ========== HARDWARE SETUP ==========
i2c = I2C(0, scl=Pin(I2C_SCL), sda=Pin(I2C_SDA), freq=800_000)

# Scan I2C bus to verify devices
print("I2C scan:", [hex(addr) for addr in i2c.scan()])

time.sleep_ms(25)  # Let I2C settle
oled = ssd1306.SSD1306_I2C(128, 64, i2c, addr=0x3c)


# ========== HTU21D SENSOR ==========
class HTU21D:
    """HTU21D temperature/humidity sensor driver with proper bit masking"""
    def __init__(self, i2c, addr=0x40):
        self.i2c = i2c
        self.addr = addr
    
    def read_temperature(self):
        """Return temperature in Celsius"""
        self.i2c.writeto(self.addr, b'\xF3')  # Trigger temp measurement (no hold)
        time.sleep_ms(50)  # Wait for measurement (max 50ms at 14-bit resolution)
        data = self.i2c.readfrom(self.addr, 3)
        # Mask out status bits (2 LSBs) before calculation
        raw = (data[0] << 8) | (data[1] & 0xFC)
        temp_c = -46.85 + (175.72 * raw / 65536.0)
        return temp_c
    
    def read_humidity(self):
        """Return relative humidity %"""
        self.i2c.writeto(self.addr, b'\xF5')  # Trigger humidity measurement
        time.sleep_ms(16)  # Wait for measurement (max 16ms at 12-bit resolution)
        data = self.i2c.readfrom(self.addr, 3)
        # Mask out status bits (2 LSBs) before calculation
        raw = (data[0] << 8) | (data[1] & 0xFC)
        rh = -6.0 + (125.0 * raw / 65536.0)
        return max(0, min(100, rh))


try:
    sensor = HTU21D(i2c)
except Exception as e:
    print("HTU21D init failed:", e)
    sensor = None


# ========== WIFI ==========
def connect_wifi():
    """Connect to WiFi, return True if successful"""
    try:
        wlan = network.WLAN(network.STA_IF)
        wlan.active(True)
        if wlan.isconnected():
            print("Already connected:", wlan.ifconfig()[0])
            return True
        
        print("Connecting to WiFi:", WIFI_SSID)
        wlan.connect(WIFI_SSID, WIFI_PASSWORD)
        
        timeout = 15
        while not wlan.isconnected() and timeout > 0:
            time.sleep(1)
            timeout -= 1
        
        if wlan.isconnected():
            print("WiFi connected:", wlan.ifconfig()[0])
            return True
        else:
            print("WiFi connection failed")
            return False
    except Exception as e:
        print("WiFi error:", e)
        return False


def sync_time_ntp():
    """Sync time with NTP server (requires WiFi)"""
    try:
        import ntptime
        ntptime.settime()
        print("Time synced via NTP")
        return True
    except Exception as e:
        print("NTP sync failed:", e)
        return False


# ========== OPENWEATHER ==========
def fetch_outdoor_weather():
    """Fetch outdoor temp, humidity, condition from OpenWeather API.
    Returns: (temp_c, humidity%, condition_string)
    """
    if OPENWEATHER_API_KEY == "your_api_key_here":
        return None, None, None  # Skip if placeholder
    
    try:
        url = "http://api.openweathermap.org/data/2.5/weather?lat=%s&lon=%s&appid=%s&units=metric" % (
            OPENWEATHER_LAT, OPENWEATHER_LON, OPENWEATHER_API_KEY
        )
        print("Fetching weather for lat/lon:", OPENWEATHER_LAT, OPENWEATHER_LON)
        response = urequests.get(url, timeout=10)
        
        # Check HTTP status
        if response.status_code != 200:
            print("Weather API error: HTTP", response.status_code)
            if response.status_code == 401:
                print("API key invalid or not activated. Check:")
                print("  1. Key is correct: https://home.openweathermap.org/api_keys")
                print("  2. Wait 10-120 min for new key activation")
                print("  3. Free tier includes current weather API")
            response.close()
            return None, None, None
        
        # Parse JSON carefully
        try:
            data = response.json()
        except ValueError as e:
            print("Weather JSON parse error:", e)
            print("Response text:", response.text[:200])
            response.close()
            return None, None, None
        
        response.close()
        
        # Check for API error response
        if "cod" in data and str(data["cod"]) != "200":
            print("Weather API returned error:", data.get("message", "Unknown"))
            return None, None, None
        
        temp = None
        humidity = None
        condition = None
        if "main" in data:
            temp = data["main"].get("temp")
            humidity = data["main"].get("humidity")
        if "weather" in data and len(data["weather"]) > 0:
            condition = data["weather"][0].get("main")
        
        print("Weather fetched: %s, %s°C, %s%%" % (condition, temp, humidity))
        return temp, humidity, condition
    except Exception as e:
        print("Weather fetch error:", e)
        return None, None, None


# ========== SPRITE DRAWING ==========
def blit_bitmap(buf, bw, bh, dx, dy, color=1):
    """Draw 1-bit bitmap at (dx, dy)"""
    row_bytes = (bw + 7) // 8
    for y in range(bh):
        base = y * row_bytes
        for x in range(bw):
            byte_index = base + (x // 8)
            bit_pos = 7 - (x % 8)
            on = (buf[byte_index] >> bit_pos) & 1
            if on:
                px = dx + x
                py = dy + y
                if 0 <= px < 128 and 0 <= py < 64:
                    oled.pixel(px, py, color)


# ========== GAME STATE ==========
current_mood = MOOD_HAPPY
frame_idx = 0
indoor_temp_c = None
indoor_humidity = None
outdoor_temp_c = None
outdoor_humidity = None
weather_condition = None  # "Rain" or "Clear"
manual_rain_mode = False  # Toggle rain overlay manually with button
last_mood_change = 0
last_weather_update = 0
last_stat_decay = 0

STATE_IDLE = "idle"
STATE_MENU = "menu"
STATE_STATS = "stats"
STATE_MESSAGE = "message"
STATE_MINIGAME = "minigame"

STAT_KEYS = ("Energy", "Hunger", "Health")
stats_values = {
    "Energy": 80,
    "Hunger": 65,
    "Health": 75,
}
STAT_MIN = 0
STAT_MAX = 100
STAT_DECAY_INTERVAL_MS = 120000  # 2 minutes
STAT_DECAY_AMOUNT = 1

# Sensor calibration (adjust based on known accurate readings)
TEMP_OFFSET_C = 0  # Temperature offset in Celsius
HUMIDITY_OFFSET = 0 


def c_to_f(celsius):
    """Convert Celsius to Fahrenheit"""
    if celsius is None:
        return None
    return celsius * 9.0 / 5.0 + 32.0


def clamp(value, low, high):
    if value < low:
        return low
    if value > high:
        return high
    return value


def clamp_stat(value):
    return clamp(value, STAT_MIN, STAT_MAX)


def get_stat(name):
    return clamp_stat(stats_values.get(name, 0))


def set_stat(name, value):
    stats_values[name] = clamp_stat(int(value))


def adjust_stat(name, delta):
    stats_values[name] = clamp_stat(stats_values.get(name, 0) + delta)


def decay_stats(amount):
    for key in STAT_KEYS:
        stats_values[key] = clamp_stat(stats_values.get(key, 0) - amount)


def get_time_string(show_colon=True):
    """Get current time as formatted string with optional blinking colon.
    Returns: (time_string, period_string) e.g., ("9:45" or "9 45", "AM")
    """
    try:
        # Get current UTC time and apply timezone offset
        utc_seconds = time.time()
        local_seconds = utc_seconds + (TIMEZONE_OFFSET * 3600)
        t = time.localtime(local_seconds)
        
        hour = t[3]  # 0-23
        minute = t[4]
        # Convert to 12-hour format
        if hour == 0:
            hour_12 = 12
            period = "AM"
        elif hour < 12:
            hour_12 = hour
            period = "AM"
        elif hour == 12:
            hour_12 = 12
            period = "PM"
        else:
            hour_12 = hour - 12
            period = "PM"
        
        # Use colon or space for blinking effect
        separator = ":" if show_colon else " "
        time_str = "%d%s%02d" % (hour_12, separator, minute)
        return time_str, period
    except Exception as e:
        print("Time format error:", e)
        return "--:--", ""


def update_sensors():
    """Read indoor temperature and humidity from HTU21D with calibration"""
    global indoor_temp_c, indoor_humidity
    if sensor:
        try:
            raw_temp = sensor.read_temperature()
            raw_humidity = sensor.read_humidity()
            indoor_temp_c = raw_temp + TEMP_OFFSET_C  # Apply temp calibration
            indoor_humidity = max(0, min(100, raw_humidity + HUMIDITY_OFFSET))  # Apply humidity calibration (clamp 0-100%)
        except Exception as e:
            print("Sensor read error:", e)
            indoor_temp_c = None
            indoor_humidity = None


def update_weather():
    """Fetch outdoor temp, humidity, and condition from OpenWeather"""
    global outdoor_temp_c, outdoor_humidity, weather_condition, last_weather_update
    try:
        outdoor_temp_c, outdoor_humidity, weather_condition = fetch_outdoor_weather()
    except Exception as e:
        print("Weather update error:", e)
        outdoor_temp_c = None
        outdoor_humidity = None
        weather_condition = None
    last_weather_update = time.ticks_ms()


def change_mood():
    """Change pet mood with 50% chance"""
    global current_mood
    import random
    # 50% chance to actually change mood
    if random.random() < 0.5:
        moods = [MOOD_HAPPY, MOOD_SAD, MOOD_BORED, MOOD_LOVE, MOOD_POUTING]
        current_mood = random.choice(moods)
        print("Mood changed to:", current_mood)
    else:
        print("Mood change skipped (50% chance)")


def draw_rain_overlay():
    """Draw simple rain overlay (diagonal lines)"""
    import random
    for _ in range(19):  # 19 random raindrops
        x = random.randint(0, 127)
        y = random.randint(0, 63)
        # Small diagonal line
        for i in range(4):
            px, py = x + i, y + i
            if 0 <= px < 128 and 0 <= py < 64:
                oled.pixel(px, py, 1)


def is_rain_mode_enabled():
    return manual_rain_mode


def toggle_rain_mode():
    global manual_rain_mode
    manual_rain_mode = not manual_rain_mode


def render():
    """Draw the full screen: pet + temps/humidity + weather overlay"""
    oled.fill(0)
    
    # Time display in upper left corner with blinking colon
    # Blink based on current second (on for even seconds, off for odd)
    try:
        # Apply timezone offset for proper local time display
        utc_seconds = time.time()
        local_seconds = utc_seconds + (TIMEZONE_OFFSET * 3600)
        second = time.localtime(local_seconds)[5]
        show_colon = (second % 2) == 0
    except:
        show_colon = True
    
    time_str, period = get_time_string(show_colon)
    oled.text(time_str, 0, 0, 1)
    
    # AM/PM in upper right corner
    if period:
        # Right-align: 128 pixels wide, each char is 8 pixels, "AM"/"PM" is 2 chars = 16 pixels + 1 spacing
        oled.text(period, (128 - 18), 0, 1)
    
    # Pet sprite centered
    pet_x = (128 - PET_W) // 2
    pet_y = 0
    frames = MOOD_FRAMES[current_mood]
    blit_bitmap(frames[frame_idx % len(frames)], PET_W, PET_H, pet_x, pet_y, 1)
    
    # Rain overlay if actual weather is rainy OR manual rain mode enabled
    show_rain = (weather_condition and weather_condition in ("Rain", "Drizzle", "Thunderstorm")) or manual_rain_mode
    if show_rain:
        draw_rain_overlay()
    
    # Weather icons (32x32) above temperatures
    # House icon for indoor (left side)
    blit_bitmap(HOUSE_ICON, ICON_W, ICON_H, 0, 10, 1)
    # Sun icon for outdoor (right side)
    blit_bitmap(SUN_ICON, ICON_W, ICON_H, 32+64-2, 10, 1)   #Have no idea why i need the minus 2px but the image gets cut off witout it...
    
    # Left side: Indoor temp and humidity
    if indoor_temp_c is not None:
        indoor_f = c_to_f(indoor_temp_c)
        oled.text("%dF" % int(indoor_f), 0, 48, 1)
    else:
        oled.text("--F", 0, 48, 1)
    
    if indoor_humidity is not None:
        oled.text("%d%%" % int(indoor_humidity), 0, 56, 1)
    else:
        oled.text("--%", 0, 56, 1)
    
    # Right side: Outdoor temp and humidity
    if outdoor_temp_c is not None:
        outdoor_f = c_to_f(outdoor_temp_c)
        oled.text("%dF" % int(outdoor_f), 98, 48, 1)
    else:
        oled.text("--F", 98, 48, 1)
    
    if outdoor_humidity is not None:
        oled.text("%d%%" % int(outdoor_humidity), 98, 56, 1)
    else:
        oled.text("--%", 98, 56, 1)
    
    oled.show()


def _center_x(text):
    return max(0, (128 - len(text) * 8) // 2)


def format_menu_label(item):
    label = item.get("label", "")
    item_type = item.get("type")
    if item_type == "submenu":
        return "%s >" % label
    if item_type == "toggle":
        getter = item.get("getter")
        value = False
        if getter:
            try:
                value = bool(getter())
            except Exception as exc:
                print("Toggle getter error:", exc)
        return "%s: %s" % (label, "On" if value else "Off")
    if item_type == "back":
        return "< Back"
    return label


def render_menu_screen(menu):
    oled.fill(0)
    title = menu.title or "Menu"
    oled.text(title, _center_x(title), 0, 1)
    visible_items = menu.get_visible_items()
    start_index = menu.view_offset

    for idx, item in enumerate(visible_items):
        y = 18 + idx * 14
        label = format_menu_label(item)
        if start_index + idx == menu.index:
            oled.fill_rect(0, y - 2, 126, 12, 1)
            oled.text(label, 6, y, 0)
        else:
            oled.text(label, 6, y, 1)

    if menu.view_offset > 0:
        oled.text("^", 118, 8, 1)
    if menu.view_offset + menu.visible_count < len(menu.items):
        oled.text("v", 118, 54, 1)

    oled.text("Click to select", 6, 56, 1)
    oled.show()


def render_stats_screen():
    oled.fill(0)
    #oled.text("Stats", _center_x("Stats"), 0, 1)

    bar_x = 0
    bar_width = 115
    bar_height = 5
    row_spacing = 20

    for idx, key in enumerate(STAT_KEYS):
        value = get_stat(key)
        label_y = 10 + idx * row_spacing
        bar_y = label_y + 8
        oled.text(key, bar_x, label_y, 1)
        oled.rect(bar_x, bar_y, bar_width, bar_height, 1)
        filled = int((value * bar_width) // 100)
        if filled > 0:
            inner_width = filled - 2 if filled > 2 else filled
            inner_width = max(1, inner_width)
            oled.fill_rect(bar_x + 1, bar_y + 1, inner_width, bar_height - 2, 1)
        value_str = "%3d" % value
        oled.text(value_str, bar_x + bar_width - 24, label_y, 1)

    #oled.text("Click to return", 6, 56, 1)
    oled.show()


def render_message_screen(title, subtitle=None):
    oled.fill(0)
    oled.text(title, _center_x(title), 22, 1)
    if subtitle:
        oled.text(subtitle, _center_x(subtitle), 38, 1)
    oled.text("Click to continue", 4, 56, 1)
    oled.show()


def render_minigame_banner(game_name, status):
    oled.fill(0)
    oled.text(game_name, _center_x(game_name), 20, 1)
    oled.text(status, _center_x(status), 36, 1)
    oled.show()


def handle_feed_action():
    global current_mood, last_mood_change, frame_idx
    adjust_stat("Hunger", 25)
    adjust_stat("Health", 5)
    current_mood = MOOD_HAPPY
    frame_idx = 0
    last_mood_change = time.ticks_ms()


def handle_play_action():
    global current_mood, last_mood_change, frame_idx
    adjust_stat("Energy", -10)
    adjust_stat("Hunger", -5)
    adjust_stat("Health", 8)
    current_mood = MOOD_LOVE
    frame_idx = 0
    last_mood_change = time.ticks_ms()


def handle_doctor_action():
    global current_mood, last_mood_change, frame_idx
    adjust_stat("Health", 25)
    adjust_stat("Energy", 5)
    current_mood = MOOD_POUTING
    frame_idx = 0
    last_mood_change = time.ticks_ms()


# Device/system actions
def handle_soft_reset():
    try:
        print("Soft reset requested - rebooting device...")
        time.sleep_ms(200)
    except Exception:
        pass
    machine.reset()


# ========== MENU BUILDERS ==========
def build_menu_structure():
    minigames_menu = Menu(
        "Minigames",
        [
            {"label": "React Time", "type": "minigame", "module": minigame_a},
            {"label": "Count 2 10", "type": "minigame", "module": minigame_b},
            {"label": "Spin", "type": "minigame", "module": minigame_c},
            {"label": "Back", "type": "back"},
        ],
        visible_count=MENU_VISIBLE_COUNT,
    )

    pet_menu = Menu(
        "Pet",
        [
            {"label": "Feed", "type": "action", "handler": handle_feed_action, "message": "Feeding", "subtitle": "Yum!"},
            {"label": "Play", "type": "submenu", "submenu": minigames_menu},
            {"label": "Doctor", "type": "action", "handler": handle_doctor_action, "message": "Doctor visit", "subtitle": "All better"},
            {"label": "Back", "type": "back"},
        ],
        visible_count=MENU_VISIBLE_COUNT,
    )

    settings_menu = Menu(
        "Settings",
        [
            {"label": "Rain", "type": "toggle", "toggle": toggle_rain_mode, "getter": is_rain_mode_enabled},
            {"label": "Soft Reset", "type": "action", "handler": handle_soft_reset, "message": "Rebooting", "subtitle": "See you soon!"},
            {"label": "Back", "type": "back"},
        ],
        visible_count=MENU_VISIBLE_COUNT,
    )

    minigames_menu.set_parent(pet_menu)
    pet_menu.set_parent(None)
    settings_menu.set_parent(None)

    main_menu = Menu(
        "Menu",
        [
            {"label": "Pet", "type": "submenu", "submenu": pet_menu},
            {"label": "Stats", "type": "state", "state": STATE_STATS},
            {"label": "Settings", "type": "submenu", "submenu": settings_menu},
        ],
        visible_count=MENU_VISIBLE_COUNT,
    )

    pet_menu.set_parent(main_menu)
    settings_menu.set_parent(main_menu)

    return main_menu


def run_minigame(module, encoder):
    game_name = getattr(module, "GAME_NAME", "Minigame")
    render_minigame_banner(game_name, "Starting...")
    time.sleep_ms(400)

    try:
        encoder.reset()
    except AttributeError:
        pass
    except Exception as exc:
        print("Encoder reset failed before game:", exc)

    try:
        module.main_loop(oled, encoder)
    except Exception as exc:
        print("Minigame error:", exc)
        render_minigame_banner(game_name, "Error")
        time.sleep_ms(1200)

    try:
        encoder.reset()
    except AttributeError:
        pass
    except Exception as exc:
        print("Encoder reset failed after game:", exc)

    render_minigame_banner(game_name, "Finished")
    time.sleep_ms(300)
    return game_name


# ========== MAIN LOOP ==========
def main():
    global frame_idx, last_mood_change, last_weather_update, manual_rain_mode, last_stat_decay

    oled.fill(0)
    oled.text("Tomogatchi", (64 - (10 * 4)), 24)
    oled.text("Starting!", (64 - (9 * 4)), (24 + 8 + 1))
    oled.show()

    # Ensure any saved STA credentials are cleared before attempting fresh connect
    try:
        sta = network.WLAN(network.STA_IF)
        sta.active(True)
        try:
            sta.disconnect()
        except Exception:
            pass
        # On newer MicroPython builds, this limits auto-retries which can keep old creds alive
        try:
            sta.config(reconnects=0)
        except Exception:
            pass
        time.sleep_ms(50)
        print("Cleared WiFi STA state at boot.")
    except Exception as e:
        print("WiFi clear failed:", e)

    wifi_ok = connect_wifi()

    oled.fill(0)
    if wifi_ok:
        oled.text("WiFi OK", 32, 24)
        sync_time_ntp()
    else:
        oled.text("WiFi Failed", 16, 24)
    oled.show()

    update_sensors()
    if wifi_ok:
        update_weather()

    encoder = RotaryEncoder(ROTARY_PIN_A, ROTARY_PIN_B, ROTARY_BUTTON_PIN)

    print("Starting encoder polling thread on Core 0...")
    _thread.start_new_thread(encoder_polling_loop, (encoder,))
    time.sleep_ms(30)

    main_menu = build_menu_structure()

    now = time.ticks_ms()
    last_frame_sw = now
    last_mood_change = now
    last_weather_update = now
    last_render = now
    last_sensor_update = now
    last_stat_decay = now

    current_state = STATE_IDLE
    state_entered_at = now
    menu_last_interaction = now
    menu_stack = []
    menu_after_message = []
    message_text = ""
    message_subtext = None
    message_return_state = STATE_IDLE
    pending_minigame = None
    minigame_return_menu_stack = []

    try:
        while True:
            now = time.ticks_ms()
            delta, clicked = encoder.read()

            if delta != 0:
                direction = "CW" if delta > 0 else "CCW"
                print("Encoder: %s (delta=%d)" % (direction, delta))
            if clicked:
                print("Encoder: Button clicked")

            if time.ticks_diff(now, last_sensor_update) >= SENSOR_UPDATE_INTERVAL_MS:
                update_sensors()
                last_sensor_update = now

            if time.ticks_diff(now, last_mood_change) >= MOOD_CHANGE_INTERVAL:
                change_mood()
                last_mood_change = now

            if wifi_ok and time.ticks_diff(now, last_weather_update) >= WEATHER_UPDATE_INTERVAL:
                update_weather()
                last_weather_update = now

            if time.ticks_diff(now, last_stat_decay) >= STAT_DECAY_INTERVAL_MS:
                decay_stats(STAT_DECAY_AMOUNT)
                last_stat_decay = now

            if time.ticks_diff(now, last_frame_sw) >= FRAME_TIME:
                frame_idx = (frame_idx + 1) % 2
                last_frame_sw = now

            if current_state == STATE_MINIGAME and pending_minigame:
                module = pending_minigame
                pending_minigame = None
                menu_preserved = list(minigame_return_menu_stack)
                game_name = run_minigame(module, encoder)
                handle_play_action()
                menu_stack = list(menu_preserved)
                menu_after_message = list(menu_stack)
                message_text = game_name
                message_subtext = "Great game!"
                message_return_state = STATE_MENU if menu_stack else STATE_IDLE
                current_state = STATE_MESSAGE
                state_entered_at = time.ticks_ms()
                menu_last_interaction = state_entered_at
                continue

            if current_state == STATE_IDLE:
                if clicked:
                    main_menu.reset()
                    main_menu.ensure_visible()
                    menu_stack = [main_menu]
                    current_state = STATE_MENU
                    state_entered_at = now
                    menu_last_interaction = now
                    clicked = False

            elif current_state == STATE_MENU:
                if not menu_stack:
                    main_menu.reset()
                    main_menu.ensure_visible()
                    menu_stack = [main_menu]
                current_menu = menu_stack[-1]
                if delta:
                    current_menu.move(delta)
                    menu_last_interaction = now
                    delta = 0
                if clicked:
                    item = current_menu.selected()
                    menu_last_interaction = now
                    clicked = False
                    if item:
                        item_type = item.get("type")
                        if item_type == "submenu":
                            submenu = item.get("submenu")
                            if submenu:
                                submenu.reset()
                                submenu.set_parent(current_menu)
                                menu_stack.append(submenu)
                        elif item_type == "back":
                            if len(menu_stack) > 1:
                                menu_stack.pop()
                                menu_stack[-1].ensure_visible()
                            else:
                                menu_stack = []
                                current_state = STATE_IDLE
                                state_entered_at = now
                        elif item_type == "state":
                            target_state = item.get("state")
                            current_state = target_state or STATE_IDLE
                            state_entered_at = now
                            if current_state == STATE_STATS:
                                menu_last_interaction = now
                        elif item_type == "toggle":
                            toggle_fn = item.get("toggle")
                            if toggle_fn:
                                toggle_fn()
                        elif item_type == "minigame":
                            module = item.get("module")
                            if module:
                                pending_minigame = module
                                minigame_return_menu_stack = list(menu_stack)
                                current_state = STATE_MINIGAME
                                state_entered_at = now
                        else:
                            handler = item.get("handler")
                            if handler:
                                handler()
                            message_text = item.get("message") or item.get("label", "Done")
                            message_subtext = item.get("subtitle")
                            menu_after_message = list(menu_stack)
                            message_return_state = STATE_MENU if menu_after_message else STATE_IDLE
                            current_state = STATE_MESSAGE
                            state_entered_at = now
                if current_state == STATE_MENU and time.ticks_diff(now, menu_last_interaction) >= MENU_IDLE_TIMEOUT_MS:
                    menu_stack = []
                    current_state = STATE_IDLE
                    state_entered_at = now

            elif current_state == STATE_STATS:
                if clicked:
                    clicked = False
                    if menu_stack:
                        current_state = STATE_MENU
                        menu_last_interaction = now
                    else:
                        current_state = STATE_IDLE
                    state_entered_at = now
                elif delta:
                    menu_last_interaction = now
                if time.ticks_diff(now, menu_last_interaction) >= MENU_IDLE_TIMEOUT_MS:
                    current_state = STATE_IDLE
                    menu_stack = []
                    state_entered_at = now

            elif current_state == STATE_MESSAGE:
                expired = time.ticks_diff(now, state_entered_at) >= ACTION_VIEW_DURATION_MS
                if clicked or expired:
                    if clicked:
                        clicked = False
                    if message_return_state == STATE_MENU and menu_after_message:
                        menu_stack = list(menu_after_message)
                        current_state = STATE_MENU
                        menu_last_interaction = now
                    else:
                        menu_stack = []
                        current_state = STATE_IDLE
                    state_entered_at = now
                    message_text = ""
                    message_subtext = None
                    menu_after_message = []

            if time.ticks_diff(now, last_render) >= RENDER_INTERVAL_MS:
                if current_state == STATE_IDLE:
                    render()
                elif current_state == STATE_MENU:
                    current_menu = menu_stack[-1] if menu_stack else main_menu
                    current_menu.ensure_visible()
                    render_menu_screen(current_menu)
                elif current_state == STATE_STATS:
                    render_stats_screen()
                elif current_state == STATE_MESSAGE:
                    render_message_screen(message_text or "Done", message_subtext)
                last_render = now

    except KeyboardInterrupt:
        oled.fill(1)
        oled.text("Stopped.", 32, 28, 0)
        oled.show()
        print("Pet stopped by user.")


if __name__ == "__main__":
    main()
