#!/bin/bash
# Auto-start librespot with saved OAuth credentials

CACHE_DIR="/home/jubers/.cache/librespot"
DEVICE_NAME="Raspberry-Pi"
BLUETOOTH_DEVICE="bluez_output.41_42_E8_0A_80_B7.1"

# Create cache directory if it doesn't exist
mkdir -p "$CACHE_DIR"

echo "Starting librespot Spotify Connect client..."
echo "Device name: $DEVICE_NAME"
echo "Audio output: $BLUETOOTH_DEVICE"

# Start librespot with cached credentials
librespot \
    --name "$DEVICE_NAME" \
    --backend pulseaudio \
    --device "$BLUETOOTH_DEVICE" \
    --bitrate 320 \
    --enable-volume-normalisation \
    --normalisation-pregain -10 \
    --initial-volume 85 \
    --disable-audio-cache \
    --enable-oauth \
    --system-cache "$CACHE_DIR" \
    --verbose