#!/usr/bin/env python3
"""
WS2812B LED Troubleshooting Script
Run with: sudo python3 test_led.py
"""
import sys
import time

print("=" * 60)
print("WS2812B LED Troubleshooting")
print("=" * 60)

# Check if running as root
import os
if os.geteuid() != 0:
    print("❌ ERROR: This script must be run as root!")
    print("   Run with: sudo python3 test_led.py")
    sys.exit(1)
else:
    print("✓ Running as root")

# Check library installation
try:
    from rpi_ws281x import PixelStrip, Color
    print("✓ rpi_ws281x library installed")
except ImportError as e:
    print(f"❌ rpi_ws281x library not found: {e}")
    print("   Install with: sudo pip3 install rpi_ws281x")
    sys.exit(1)

# Test different configurations
configs = [
    {"pin": 12, "channel": 0, "dma": 10, "invert": False},
    {"pin": 12, "channel": 0, "dma": 10, "invert": True},   # Try inverted
    {"pin": 13, "channel": 1, "dma": 10, "invert": False},
    {"pin": 18, "channel": 0, "dma": 10, "invert": False},
    {"pin": 19, "channel": 1, "dma": 10, "invert": False},
]

print("\nTrying different configurations...")
print("Watch your LED for any response!\n")

for idx, config in enumerate(configs, 1):
    print(f"\nTest {idx}: GPIO {config['pin']}, Channel {config['channel']}, "
          f"DMA {config['dma']}, Invert={config['invert']}")
    
    try:
        # Create strip
        strip = PixelStrip(
            num=1,                      # 1 LED
            pin=config['pin'],
            freq_hz=800000,
            dma=config['dma'],
            invert=config['invert'],
            brightness=255,
            channel=config['channel']
        )
        
        strip.begin()
        print("  ✓ Initialized successfully")
        
        # Test colors
        colors = [
            (255, 0, 0, "RED"),
            (0, 255, 0, "GREEN"),
            (0, 0, 255, "BLUE"),
            (255, 255, 255, "WHITE")
        ]
        
        for r, g, b, name in colors:
            print(f"  Testing {name}...", end=" ", flush=True)
            strip.setPixelColor(0, Color(r, g, b))
            strip.show()
            time.sleep(1.5)
            print("done")
        
        # Turn off
        strip.setPixelColor(0, Color(0, 0, 0))
        strip.show()
        
        response = input("\n  Did you see the LED light up? (y/n): ").lower()
        if response == 'y':
            print(f"\n🎉 SUCCESS! Use these settings:")
            print(f"   led_pin = {config['pin']}")
            print(f"   LED_CHANNEL = {config['channel']}")
            print(f"   LED_DMA = {config['dma']}")
            print(f"   LED_INVERT = {config['invert']}")
            sys.exit(0)
        
    except RuntimeError as e:
        print(f"  ❌ Failed: {e}")
    except Exception as e:
        print(f"  ❌ Unexpected error: {e}")

print("\n" + "=" * 60)
print("Troubleshooting tips:")
print("=" * 60)
print("1. Check wiring:")
print("   - LED Data pin → GPIO pin on Raspberry Pi")
print("   - LED GND → Raspberry Pi GND")
print("   - LED 5V → External 5V power (NOT from Pi if multiple LEDs)")
print()
print("2. Verify LED type:")
print("   - WS2812B expects 800kHz signal")
print("   - Some clones use different timing")
print()
print("3. Check power:")
print("   - Single LED can use Pi power")
print("   - Multiple LEDs need external 5V supply")
print("   - Ground must be common between Pi and power supply")
print()
print("4. Try a level shifter:")
print("   - Pi outputs 3.3V, LED expects 5V data signal")
print("   - May work without, but level shifter is more reliable")
print()
print("5. Test with known working setup:")
print("   - Try a different LED if available")
print("   - Test same LED with Arduino/ESP32")
print("=" * 60)
