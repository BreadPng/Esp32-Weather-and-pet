# MicroPython Pet Mood Display
**ESP32 + HTU21D Temp/Humidity Sensor + SSD1306 128×64 OLED**

A virtual pet that displays different moods based on time, shows indoor temperature from HTU21D sensor, and fetches outdoor temperature from OpenWeather API.

## Hardware Setup

### Components
- Elegoo ESP32 Development Board (CP2102, USB-C)
- HTU21D I2C Temperature/Humidity Sensor
- SSD1306 128×64 I2C OLED display
- Rotary Encoder with push button (optional, for menu navigation)

### Wiring

#### OLED (I2C, address 0x3C)
- `VCC` → ESP32 `3V3`
- `GND` → ESP32 `GND`
- `SDA` → ESP32 `GPIO21`
- `SCL` → ESP32 `GPIO22`

#### HTU21D Sensor (I2C, address 0x40)
- `VCC` → ESP32 `3V3`
- `GND` → ESP32 `GND`
- `SDA` → ESP32 `GPIO21` (shared with OLED)
- `SCL` → ESP32 `GPIO22` (shared with OLED)

#### Rotary Encoder (Optional)
- `CLK` (A) → ESP32 `GPIO18`
- `DT` (B) → ESP32 `GPIO19`
- `SW` (Button) → ESP32 `GPIO23`
- `+` → ESP32 `3V3`
- `GND` → ESP32 `GND`

Both I2C devices share the same bus (GPIO21/22).

## Software Setup

### 1. Flash MicroPython
Download ESP32 firmware from https://micropython.org/download/ESP32_GENERIC/

```bash
esptool.py --chip esp32 --port /dev/cu.usbserial-0001 erase_flash
esptool.py --chip esp32 --port /dev/cu.usbserial-0001 --baud 460800 write_flash -z 0x1000 esp32-*.bin
```

### 2. Configure WiFi and API Key

Edit `main.py` lines 13-19:
```python
WIFI_SSID = "YourNetworkName"
WIFI_PASSWORD = "YourPassword"
OPENWEATHER_API_KEY = "your_api_key_here"  # Get free key at https://openweathermap.org/api
OPENWEATHER_CITY = "San Francisco,US"  # or "London,UK", etc.
```

### 3. Upload Files

Using the paste-mode uploader (no raw REPL needed):
```bash
conda activate mp-esp32
python upload_via_paste.py /dev/cu.usbserial-0001
```

Or use MicroPico extension in VS Code:
- Command Palette → "MicroPico: Upload project to Pico"

### 4. Run

The code auto-runs on boot if saved as `main.py`. To run manually:
```bash
mpremote connect /dev/cu.usbserial-0001 run :main.py
```

## Features

### Pet Moods (5 total, 2-frame animations each)
- **Happy**: Wide eyes, big smile
- **Sad**: Droopy eyes, frown
- **Bored**: Half-closed eyes, yawn
- **Love**: Heart eyes, smile
- **Pouting**: Angry eyebrows, puffed cheeks

### Display Layout
- **Top**: 64×64 pixel pet sprite (center-aligned)
- **Bottom left**: Indoor temperature (°F) from HTU21D
- **Bottom right**: Outdoor temperature (°F) from OpenWeather

### Behavior
- **Animation**: 500ms per frame (2 frames per mood)
- **Mood changes**: Every 15 minutes (random for now; can add logic later)
- **Weather updates**: Every 10 minutes via WiFi
- **Sensor reads**: Continuous (HTU21D temperature/humidity)

## Files

- **`main.py`**: Main loop, WiFi, sensors, OpenWeather, rendering
- **`sprites.py`**: 5 moods × 2 frames (64×64 ASCII art)
- **`ssd1306.py`**: I2C OLED driver
- **`config.py`**: WiFi, API keys, and hardware configuration
- **`menu.py`**: Menu system for navigation
- **`rotary_encoder.py`**: Polling-based rotary encoder (default)
- **`rotary_encoder_irq.py`**: Hardware-based rotary encoder (ESP32 PCNT)
- **`minigame_*.py`**: Mini-games accessible via menu
- **`upload_to_esp32.py`**: Upload script for deploying to ESP32

## Rotary Encoder Configuration

Two encoder implementations available (switch via `USE_HARDWARE_ENCODER` in `config.py`):

### Polling Encoder (Default)
- File: `rotary_encoder.py`
- No setup required
- Works immediately

### Hardware Encoder (Recommended)
- File: `rotary_encoder_irq.py`
- Uses ESP32 PCNT hardware (lower CPU, more reliable)
- Setup:
  ```bash
  # Install library (one-time)
  mpremote mip install github:miketeachman/micropython-rotary
  ```
  ```python
  # In config.py
  USE_HARDWARE_ENCODER = True
  ```

## Customization

### Change Mood Logic
Edit `change_mood()` in `main.py` (line ~155):
```python
def change_mood():
    global current_mood
    # Example: sad if too hot
    if indoor_temp_c and indoor_temp_c > 30:
        current_mood = MOOD_SAD
    # Example: happy if comfortable
    elif indoor_temp_c and 20 <= indoor_temp_c <= 25:
        current_mood = MOOD_HAPPY
    else:
        import random
        current_mood = random.choice([MOOD_BORED, MOOD_LOVE, MOOD_POUTING])
```

### Change Animation Speed
Edit `FRAME_TIME` in `main.py` (line 23):
```python
FRAME_TIME = 500  # ms per frame (default 500ms)
```

### Change Mood Interval
Edit `MOOD_CHANGE_INTERVAL` in `main.py` (line 24):
```python
MOOD_CHANGE_INTERVAL = 15 * 60 * 1000  # 15 minutes (in milliseconds)
```

### Add New Moods
1. Add ASCII art frames to `sprites.py` (64×64, 2 frames)
2. Define new mood constant: `MOOD_EXCITED = const(5)`
3. Add to `MOOD_FRAMES` dict
4. Update `change_mood()` logic

### Edit Pet Sprites
Edit ASCII art in `sprites.py`. Use `#` for pixels, `.` for empty. Each mood needs exactly 2 frames of 64 lines × 64 characters.

## Troubleshooting

### Display blank
- Check wiring: SDA/SCL to GPIO21/22, VCC to 3V3
- Run I2C scan:
  ```python
  from machine import Pin, I2C
  i2c = I2C(0, scl=Pin(22), sda=Pin(21), freq=100000)
  print([hex(a) for a in i2c.scan()])  # expect ['0x3c', '0x40']
  ```

### HTU21D not found
- Check sensor wiring (shares I2C bus with OLED)
- I2C scan should show `0x40` (HTU21D address)
- Try slower I2C frequency: `freq=50000`

### WiFi connection failed
- Double-check SSID and password in `main.py`
- Ensure 2.4GHz WiFi (ESP32 doesn't support 5GHz)
- Check signal strength

### Weather not updating
- Verify OpenWeather API key is valid (free tier: 60 calls/min)
- Check city name format: `"CityName,CountryCode"` (e.g., `"London,UK"`)
- Monitor serial output for error messages

### Upload fails
- Close any open REPL/serial connections
- Try: `python upload_via_paste.py /dev/cu.usbserial-0001`
- If still fails, manually paste files in REPL (Ctrl-E paste mode)

## API Key Setup

1. Go to https://openweathermap.org/api
2. Sign up for free account
3. Generate API key (takes ~10 minutes to activate)
4. Copy key to `OPENWEATHER_API_KEY` in `main.py`

## Future Enhancements

- Add mood logic based on temperature thresholds
- Display humidity from HTU21D
- Add time-of-day moods (sleepy at night)
- Save mood history to flash
- Add simple animations (pet moves around screen)
- Display weather icons (sunny/rainy/cloudy)

## License
MIT (modify freely!)
