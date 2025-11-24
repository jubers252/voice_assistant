#!/bin/bash
# INMP441 Audio Configuration Helper for Raspberry Pi

echo "=================================================="
echo "INMP441 I2S Microphone Configuration Helper"
echo "=================================================="
echo ""

# Check if INMP441 is detected
echo "[1/5] Checking for I2S audio devices..."
arecord -l | grep -i "i2s\|card"
echo ""

# Check ALSA configuration
echo "[2/5] Checking ALSA mixer settings..."
echo "Looking for capture devices..."
amixer scontrols
echo ""

# Try to get capture volume
echo "[3/5] Current capture volume:"
amixer sget Capture 2>/dev/null || echo "No 'Capture' control found"
echo ""

# Show /boot/config.txt I2S settings
echo "[4/5] Checking /boot/config.txt for I2S configuration..."
if [ -f /boot/config.txt ]; then
    grep -E "dtoverlay.*i2s|dtparam.*i2s" /boot/config.txt || echo "No I2S overlay found in /boot/config.txt"
elif [ -f /boot/firmware/config.txt ]; then
    grep -E "dtoverlay.*i2s|dtparam.*i2s" /boot/firmware/config.txt || echo "No I2S overlay found in /boot/firmware/config.txt"
else
    echo "config.txt not found in expected locations"
fi
echo ""

# Test recording
echo "[5/5] Testing INMP441 recording..."
echo "Recording 3 seconds of audio..."
echo "Please speak into the microphone..."

# Find the I2S card
CARD=$(arecord -l | grep -i "i2s" | head -1 | sed 's/card \([0-9]\).*/\1/')

if [ -n "$CARD" ]; then
    echo "Using card $CARD"
    arecord -D plughw:$CARD,0 -f S32_LE -r 16000 -c 1 -d 3 /tmp/test_inmp441.wav 2>&1 | grep -v "ALSA lib"
    
    if [ -f /tmp/test_inmp441.wav ]; then
        echo ""
        echo "✓ Recording successful! File saved to /tmp/test_inmp441.wav"
        
        # Check file size
        SIZE=$(stat -f%z /tmp/test_inmp441.wav 2>/dev/null || stat -c%s /tmp/test_inmp441.wav)
        echo "  File size: $SIZE bytes"
        
        if [ $SIZE -lt 1000 ]; then
            echo "  ✗ WARNING: File is very small - microphone may not be working!"
        else
            echo "  ✓ File size looks good"
            echo ""
            echo "  You can play it back with: aplay /tmp/test_inmp441.wav"
        fi
    else
        echo "✗ Recording failed!"
    fi
else
    echo "✗ No I2S card found!"
    echo ""
    echo "Troubleshooting steps:"
    echo "1. Check INMP441 wiring:"
    echo "   - VDD  → 3.3V"
    echo "   - GND  → Ground"
    echo "   - SCK  → GPIO 18 (BCM 18 / Pin 12)"
    echo "   - WS   → GPIO 19 (BCM 19 / Pin 35)"
    echo "   - SD   → GPIO 20 (BCM 20 / Pin 38)"
    echo ""
    echo "2. Add to /boot/config.txt (or /boot/firmware/config.txt):"
    echo "   dtoverlay=i2s-mems"
    echo "   or"
    echo "   dtoverlay=googlevoicehat-soundcard"
    echo ""
    echo "3. Reboot after making changes"
fi

echo ""
echo "=================================================="
echo "Configuration check complete!"
echo "=================================================="
echo ""
echo "If the microphone is not working, run:"
echo "  sudo nano /boot/config.txt"
echo "Add this line:"
echo "  dtoverlay=i2s-mems"
echo "Then reboot: sudo reboot"
echo ""
echo "To adjust capture volume (if available):"
echo "  alsamixer"
echo "  Press F4 for Capture, then use arrow keys to adjust"
echo "=================================================="
