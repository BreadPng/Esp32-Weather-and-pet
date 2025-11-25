#!/usr/bin/env python3
"""
Upload files to ESP32 running MicroPython.

This script uploads all necessary Python files to the ESP32 device.
It tries mpremote first (recommended), then falls back to ampy if available.

Usage:
    python upload_to_esp32.py [port] [options]
    
Examples:
    python upload_to_esp32.py
    python upload_to_esp32.py /dev/cu.usbserial-0001
    python upload_to_esp32.py COM3
    python upload_to_esp32.py --skip-config  # Skip config.py upload
    python upload_to_esp32.py --check-storage  # Check storage after upload
    python upload_to_esp32.py --monitor  # View device logs after upload
    python upload_to_esp32.py --monitor --monitor-duration 30  # Monitor for 30 seconds
"""

import sys
import os
import subprocess
import argparse
from pathlib import Path


# Files to upload (in order - main.py should be last to run on boot)
FILES_TO_UPLOAD = [
    "ssd1306.py",
    "sprites.py",
    "menu.py",
    "rotary_encoder.py",
    "config.py",
    "main.py",
    "minigame_a.py",
    "minigame_b.py",
    "minigame_c.py",
    
]

# Files to skip
FILES_TO_SKIP = [
    "config.py.example",
    "image_to_ascii.py",
    "README.md",
    "upload_to_esp32.py",
]


def find_esp32_port():
    """Try to automatically detect ESP32 serial port."""
    import serial.tools.list_ports
    
    # Common ESP32 vendor IDs
    esp32_vids = [0x10C4, 0x303A, 0x1A86, 0x2341]  # CP2102, ESP32, CH340, Arduino
    
    ports = serial.tools.list_ports.comports()
    for port in ports:
        if port.vid in esp32_vids or 'ESP32' in port.description.upper() or 'CP210' in port.description.upper():
            return port.device
    
    # Fallback: list all ports
    if ports:
        print("\nAvailable ports:")
        for port in ports:
            print(f"  {port.device} - {port.description}")
        return ports[0].device if ports else None
    
    return None


def check_command(command):
    """Check if a command is available."""
    try:
        subprocess.run([command, "--version"], 
                      capture_output=True, 
                      check=True, 
                      timeout=5)
        return True
    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
        return False


def upload_with_mpremote(port, files):
    """Upload files using mpremote."""
    print(f"Using mpremote to upload to {port}...")
    
    failed = []
    for file in files:
        if not os.path.exists(file):
            print(f"⚠️  Warning: {file} not found, skipping...")
            continue
        
        print(f"📤 Uploading {file}...", end=" ", flush=True)
        try:
            result = subprocess.run(
                ["mpremote", "connect", port, "cp", file, f":{file}"],
                capture_output=True,
                text=True,
                timeout=30
            )
            
            if result.returncode == 0:
                print("✓")
            else:
                print(f"✗ Error: {result.stderr}")
                failed.append(file)
        except subprocess.TimeoutExpired:
            print("✗ Timeout")
            failed.append(file)
        except Exception as e:
            print(f"✗ Error: {e}")
            failed.append(file)
    
    return failed


def upload_with_ampy(port, files):
    """Upload files using ampy."""
    print(f"Using ampy to upload to {port}...")
    
    failed = []
    for file in files:
        if not os.path.exists(file):
            print(f"⚠️  Warning: {file} not found, skipping...")
            continue
        
        print(f"📤 Uploading {file}...", end=" ", flush=True)
        try:
            result = subprocess.run(
                ["ampy", "--port", port, "put", file],
                capture_output=True,
                text=True,
                timeout=30
            )
            
            if result.returncode == 0:
                print("✓")
            else:
                print(f"✗ Error: {result.stderr}")
                failed.append(file)
        except subprocess.TimeoutExpired:
            print("✗ Timeout")
            failed.append(file)
        except Exception as e:
            print(f"✗ Error: {e}")
            failed.append(file)
    
    return failed


def monitor_serial(port, duration=None):
    """Monitor serial output from the ESP32."""
    try:
        import serial
        import time
        
        print(f"\n📟 Connecting to serial monitor on {port}...")
        print("=" * 60)
        print("Press Ctrl+C to exit\n")
        
        ser = serial.Serial(port, 115200, timeout=1)
        start_time = time.time()
        
        try:
            while True:
                if ser.in_waiting > 0:
                    data = ser.read(ser.in_waiting)
                    try:
                        print(data.decode('utf-8'), end='', flush=True)
                    except UnicodeDecodeError:
                        # Handle binary data gracefully
                        print(data.decode('utf-8', errors='replace'), end='', flush=True)
                
                # If duration is set, exit after that time
                if duration and (time.time() - start_time) >= duration:
                    break
                    
                time.sleep(0.01)  # Small delay to prevent CPU spinning
                
        except KeyboardInterrupt:
            print("\n\n" + "=" * 60)
            print("Serial monitor closed")
        finally:
            ser.close()
            
    except ImportError:
        print("pyserial not installed. Install it with: pip install pyserial")
        return False
    except serial.SerialException as e:
        print(f"Could not open serial port: {e}")
        print("The device might be in use by another program.")
        return False
    except Exception as e:
        print(f"Error monitoring serial: {e}")
        return False
    
    return True


def check_storage(port):
    """Check ESP32 filesystem storage usage."""
    print("\nChecking storage...", end=" ", flush=True)
    
    try:
        if check_command("mpremote"):
            # Execute Python code on device to get filesystem stats
            result = subprocess.run(
                ["mpremote", "connect", port, "exec",
                 "import os; s=os.statvfs('/'); b=s[0]; t=s[2]*b; f=s[3]*b; u=t-f; print(f'{u},{f},{t}')"],
                capture_output=True,
                text=True,
                timeout=10
            )
            
            if result.returncode == 0:
                output = result.stdout.strip()
                # Parse the output: used,free,total
                try:
                    used, free, total = map(int, output.split(','))
                    used_mb = used / (1024 * 1024)
                    free_mb = free / (1024 * 1024)
                    total_mb = total / (1024 * 1024)
                    used_percent = (used / total * 100) if total > 0 else 0
                    
                    print("✓")
                    print(f"   Used:  {used_mb:.2f} MB / {total_mb:.2f} MB ({used_percent:.1f}%)")
                    print(f"   Free:  {free_mb:.2f} MB")
                    return True
                except (ValueError, IndexError) as e:
                    print(f"⚠️  Could not parse storage info: {e}")
                    return False
            else:
                print("⚠️  Could not retrieve storage info")
                return False
        else:
            print("⚠️  mpremote not available")
            return False
    except Exception as e:
        print(f"⚠️  Error checking storage: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(
        description="Upload MicroPython files to ESP32",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python upload_to_esp32.py
  python upload_to_esp32.py /dev/cu.usbserial-0001
  python upload_to_esp32.py COM3
  python upload_to_esp32.py --check-storage
  python upload_to_esp32.py --monitor
  python upload_to_esp32.py --monitor --monitor-duration 30
  python upload_to_esp32.py --skip-config --monitor --check-storage
  
Note: The device does not automatically restart. You'll need to manually
restart it or it will auto-run main.py on the next boot.
        """
    )
    parser.add_argument(
        "port",
        nargs="?",
        help="Serial port (e.g., /dev/cu.usbserial-0001 or COM3). Auto-detects if not provided."
    )
    parser.add_argument(
        "--skip-config",
        action="store_true",
        help="Skip uploading config.py (useful if you've already configured it)"
    )
    parser.add_argument(
        "--check-storage",
        action="store_true",
        help="Check and display ESP32 storage usage after upload"
    )
    parser.add_argument(
        "--monitor",
        action="store_true",
        help="Connect to serial monitor after upload to view logs (press Ctrl+C to exit)"
    )
    parser.add_argument(
        "--monitor-duration",
        type=int,
        metavar="SECONDS",
        help="Auto-exit serial monitor after N seconds (default: infinite, exit with Ctrl+C)"
    )
    
    args = parser.parse_args()
    
    # Determine port
    port = args.port
    if not port:
        try:
            import serial.tools.list_ports
            port = find_esp32_port()
            if not port:
                print("❌ Could not auto-detect ESP32 port.")
                print("Please specify the port manually:")
                print("  python upload_to_esp32.py /dev/cu.usbserial-0001")
                sys.exit(1)
            print(f"🔍 Auto-detected port: {port}")
        except ImportError:
            print("❌ pyserial not installed. Install it with: pip install pyserial")
            print("Or specify the port manually:")
            print("  python upload_to_esp32.py /dev/cu.usbserial-0001")
            sys.exit(1)
    
    # Check which files exist
    files_to_upload = []
    for file in FILES_TO_UPLOAD:
        if args.skip_config and file == "config.py":
            print(f"⏭️  Skipping {file} (--skip-config flag)")
            continue
        
        if file in FILES_TO_SKIP:
            continue
        
        if os.path.exists(file):
            files_to_upload.append(file)
        else:
            print(f"⚠️  Warning: {file} not found")
    
    if not files_to_upload:
        print("❌ No files to upload!")
        sys.exit(1)
    
    print(f"\n📋 Files to upload ({len(files_to_upload)}):")
    for file in files_to_upload:
        print(f"  - {file}")
    print()
    
    # Check for required commands
    use_mpremote = check_command("mpremote")
    if use_mpremote:
        failed = upload_with_mpremote(port, files_to_upload)
    elif check_command("ampy"):
        print("⚠️  mpremote not found, using ampy instead...")
        failed = upload_with_ampy(port, files_to_upload)
    else:
        print("❌ Neither mpremote nor ampy found!")
        print("\nPlease install one of the following:")
        print("  pip install mpremote  (recommended)")
        print("  pip install adafruit-ampy")
        sys.exit(1)
    
    # Summary
    print()
    if failed:
        print(f"❌ Upload completed with {len(failed)} error(s):")
        for file in failed:
            print(f"  - {file}")
        sys.exit(1)
    else:
        print("✅ All files uploaded successfully!")
        
        # Check storage usage if requested
        if args.check_storage:
            check_storage(port)
        
        print(f"\n📝 Next steps:")
        print(f"  1. Restart manually or the device will auto-run main.py on boot")
        print(f"  2. Connect to REPL: mpremote connect {port}")
        print(f"  3. Or run main.py: mpremote connect {port} run :main.py")
        
        # Connect to serial monitor if requested
        if args.monitor:
            monitor_serial(port, duration=args.monitor_duration)


if __name__ == "__main__":
    main()

