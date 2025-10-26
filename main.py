from machine import Pin, I2C, RTC
import time
import network
import urequests
import ssd1306
from sprites import (
    PET_W, PET_H, MOOD_FRAMES,
    MOOD_HAPPY, MOOD_SAD, MOOD_BORED, MOOD_LOVE, MOOD_POUTING,
    ICON_W, ICON_H, HOUSE_ICON, SUN_ICON
)
# Import sensitive configuration from separate file
from config import (
    WIFI_SSID, WIFI_PASSWORD,
    OPENWEATHER_API_KEY, OPENWEATHER_LAT, OPENWEATHER_LON,
    TIMEZONE_OFFSET
)

# ========== CONFIGURATION ==========

# I2C pins
I2C_SDA = 21
I2C_SCL = 22

# Timing
FRAME_TIME = 800  # ms per animation frame
MOOD_CHANGE_INTERVAL = 5 * 60 * 1000  # 5 minutes in ms
WEATHER_UPDATE_INTERVAL = 10 * 60 * 1000  # 10 minutes in ms

# ========== HARDWARE SETUP ==========
i2c = I2C(0, scl=Pin(I2C_SCL), sda=Pin(I2C_SDA), freq=400000)

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

# Boot button (GPIO0) - safe to use as input when not holding during boot
boot_button = Pin(0, Pin.IN, Pin.PULL_UP)

# Mood cycle order for button
MOOD_CYCLE = [MOOD_HAPPY, MOOD_SAD, MOOD_BORED, MOOD_LOVE, MOOD_POUTING]

# Sensor calibration (adjust based on known accurate readings)
TEMP_OFFSET_C = 0  # Temperature offset in Celsius
HUMIDITY_OFFSET = 0 


def c_to_f(celsius):
    """Convert Celsius to Fahrenheit"""
    if celsius is None:
        return None
    return celsius * 9.0 / 5.0 + 32.0


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


def cycle_mood_manual():
    """Cycle through moods in order via button press"""
    global current_mood, manual_rain_mode
    try:
        current_idx = MOOD_CYCLE.index(current_mood)
        next_idx = (current_idx + 1) % (len(MOOD_CYCLE) + 1)  # +1 for rain mode at end
        if next_idx < len(MOOD_CYCLE):
            current_mood = MOOD_CYCLE[next_idx]
            manual_rain_mode = False
            print("Button: Mood →", current_mood)
        else:
            # End of cycle: toggle rain mode and reset to first mood
            manual_rain_mode = not manual_rain_mode
            current_mood = MOOD_CYCLE[0]
            print("Button: Rain mode →", manual_rain_mode)
    except ValueError:
        # Current mood not in cycle, reset
        current_mood = MOOD_CYCLE[0]
        manual_rain_mode = False


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
    blit_bitmap(SUN_ICON, ICON_W, ICON_H, 96, 10, 1)
    
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


# ========== MAIN LOOP ==========
def main():
    global frame_idx, last_mood_change, last_weather_update
    
    oled.fill(0)
    oled.text("Tomogatchi", (64 - (10*4)), 24)          #center align (text, (screen half width - (Characters * 8 pixels per Char / 2 to center), y )
    oled.text("Starting!", (64 - (9*4)) , (24 + 8 + 1))
    oled.show()
    
    # Connect WiFi
    wifi_ok = connect_wifi()
    
    oled.fill(0)
    if wifi_ok:
        oled.text("WiFi OK", 32, 24)
        # Sync time via NTP
        sync_time_ntp()
    else:
        oled.text("WiFi Failed", 16, 24)
    oled.show()
    #time.sleep(500)
    
    # Initial sensor read and weather fetch
    update_sensors()
    if wifi_ok:
        update_weather()
    
    last_frame_sw = time.ticks_ms()
    last_mood_change = time.ticks_ms()
    last_weather_update = time.ticks_ms()
    
    try:
        while True:
            now = time.ticks_ms()
            
            
            update_sensors()
            
            # Change mood every X minutes
            if time.ticks_diff(now, last_mood_change) >= MOOD_CHANGE_INTERVAL:
                change_mood()
                last_mood_change = now
            
            # Update weather every 10 minutes
            if wifi_ok and time.ticks_diff(now, last_weather_update) >= WEATHER_UPDATE_INTERVAL:
                update_weather()
            
            # Advance animation frame
            if time.ticks_diff(now, last_frame_sw) >= FRAME_TIME:
                frame_idx = (frame_idx + 1) % 2  # all moods have 2 frames
                last_frame_sw = now
            
            # Check button - cycle through moods in order
            if boot_button.value() == 0:  # Button pressed (active low)
                time.sleep_ms(50)  # Debounce
                if boot_button.value() == 0:  
                    cycle_mood_manual()
                    while boot_button.value() == 0:  # Wait for release
                        time.sleep_ms(50)
            
            # Render
            render()
            
            
    
    except KeyboardInterrupt:
        oled.fill(1)
        oled.text("Stopped.", 32, 28, 0)
        oled.show()
        print("Pet stopped by user.")


if __name__ == "__main__":
    main()
