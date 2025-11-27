# Librespot Setup Guide for Voice Assistant

## Overview
This guide covers setting up librespot (Spotify Connect client) with OAuth authentication and Bluetooth audio output for the Raspberry Pi voice assistant.

## Prerequisites
- Raspberry Pi with Bluetooth capability
- Spotify Premium account
- Bluetooth speaker paired and connected
- PulseAudio/PipeWire audio system

## Installation Steps

### 1. Remove Previous Spotify Clients
```bash
# Stop and disable any existing Spotify services
sudo systemctl stop raspotify
sudo systemctl disable raspotify

# Remove spotifyd if installed
sudo pkill -f spotifyd
sudo rm -rf /usr/local/bin/spotifyd /home/jubers/.config/spotifyd /home/jubers/.cache/spotifyd
```

### 2. Install Librespot via Raspotify Package
```bash
# Add Raspotify repository (contains librespot binary)
curl -sSL https://dtcooper.github.io/raspotify/key.asc | sudo apt-key add -
echo 'deb https://dtcooper.github.io/raspotify raspotify main' | sudo tee /etc/apt/sources.list.d/raspotify.list

# Update and install
sudo apt update
sudo apt install -y raspotify

# Disable the raspotify service (we'll use librespot directly)
sudo systemctl stop raspotify
sudo systemctl disable raspotify
```

### 3. Create Credential Cache Directory
```bash
mkdir -p /home/jubers/.cache/librespot
```

### 4. Initial OAuth Authentication
Run librespot with OAuth for first-time authentication:
```bash
librespot \
    --name "Raspberry-Pi" \
    --backend pulseaudio \
    --device "bluez_output.41_42_E8_0A_80_B7.1" \
    --bitrate 320 \
    --enable-volume-normalisation \
    --normalisation-pregain -10 \
    --initial-volume 85 \
    --disable-audio-cache \
    --enable-oauth \
    --system-cache /home/jubers/.cache/librespot \
    --verbose
```

This will display an OAuth URL. Copy and paste it into a browser, log in with your Spotify Premium account, and complete the authorization. The credentials will be saved to the cache directory.

### 5. Create Startup Script
Create `/home/jubers/Documents/voice_assistant/start_librespot.sh`:
```bash
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
```

Make it executable:
```bash
chmod +x /home/jubers/Documents/voice_assistant/start_librespot.sh
```

### 6. Create Systemd Service (Recommended)
For automatic startup and background operation, create a systemd service:

```bash
sudo bash -c 'cat > /etc/systemd/system/librespot.service << EOF
[Unit]
Description=Librespot Spotify Connect Client
After=network.target bluetooth.target sound.target
Wants=network.target bluetooth.target sound.target

[Service]
Type=simple
User=jubers
Group=jubers
ExecStart=/usr/bin/librespot --name "Raspberry-Pi" --backend pulseaudio --device "bluez_output.41_42_E8_0A_80_B7.1" --bitrate 320 --enable-volume-normalisation --normalisation-pregain -10 --initial-volume 85 --disable-audio-cache --enable-oauth --system-cache /home/jubers/.cache/librespot --verbose
Restart=always
RestartSec=5
Environment=HOME=/home/jubers
Environment=XDG_RUNTIME_DIR=/run/user/1000
WorkingDirectory=/home/jubers
SupplementaryGroups=audio pulse pulse-access

[Install]
WantedBy=multi-user.target
EOF'
```

Enable and start the service:
```bash
sudo systemctl daemon-reload
sudo systemctl enable librespot
sudo systemctl start librespot
```

## Configuration Details

### Audio Settings
- **Backend**: `pulseaudio` - Uses PulseAudio for audio output
- **Device**: `bluez_output.41_42_E8_0A_80_B7.1` - Specific Bluetooth speaker
- **Bitrate**: `320` - High quality audio (requires Premium)
- **Volume Normalization**: Enabled with -10dB pregain
- **Initial Volume**: 85%

### Authentication
- **OAuth**: Enabled for Spotify Premium account authentication
- **Cache**: `/home/jubers/.cache/librespot` - Stores OAuth tokens
- **No Password Auth**: Modern librespot requires OAuth, not username/password

### Device Discovery
- **Zeroconf**: Automatically advertises "Raspberry-Pi" device on network
- **Avahi**: Uses Avahi for network discovery
- **Spotify Connect**: Appears in Spotify app device list

## Usage

### Starting Librespot

#### Using Systemd Service (Recommended)
```bash
# Start the service
sudo systemctl start librespot

# Check status
sudo systemctl status librespot

# View logs
sudo journalctl -u librespot -f
```

#### Using Manual Script
```bash
cd /home/jubers/Documents/voice_assistant
./start_librespot.sh
```

### Connecting from Spotify App
1. Open Spotify app on phone/computer
2. Start playing music
3. Tap the "Connect to device" icon
4. Select "Raspberry-Pi" from the device list
5. Music will play through Bluetooth speaker

### Stopping Librespot

#### Systemd Service
```bash
sudo systemctl stop librespot
```

#### Manual Script  
Press `Ctrl+C` in the terminal running librespot

## Integration with Voice Assistant

### Spotify Connector Configuration
Update `setup.txt`:
```
device_name=Raspberry-Pi
```

### OAuth Cache System
**Important**: The system uses TWO separate OAuth caches:

1. **Librespot Cache**: `/home/jubers/.cache/librespot/credentials.json`
   - Used by librespot for Spotify Connect functionality
   - Stores librespot's OAuth credentials for device discovery

2. **Spotipy Cache**: `/home/jubers/Documents/voice_assistant/.cache-fh6zfkxud9q06b6j0ihhootyu`
   - Used by voice assistant's `spotify_connector.py` for Web API calls
   - Stores spotipy's OAuth tokens for music control

Both caches are needed:
- **Librespot** makes the Pi appear as "Raspberry-Pi" device in Spotify Connect
- **Spotipy** allows the voice assistant to control playback via Web API

## Troubleshooting

### Device Not Appearing
```bash
# Check if librespot is running
ps aux | grep librespot

# Check network advertisement
avahi-browse -a -t | grep -i spotify

# Restart Bluetooth if needed
sudo systemctl restart bluetooth
```

### Audio Issues
```bash
# List audio devices
pactl list sinks short

# Test Bluetooth audio directly
paplay --device=bluez_output.41_42_E8_0A_80_B7.1 /usr/share/sounds/alsa/Front_Center.wav

# Check Bluetooth connection
bluetoothctl info 41:42:E8:0A:80:B7
```

### OAuth Token Expiry
If authentication fails, remove cache and re-authenticate:
```bash
rm -rf /home/jubers/.cache/librespot
# Then run initial OAuth setup again
```

## Key Features

✅ **No Authorization Prompts** - Credentials cached after first setup
✅ **High Quality Audio** - 320kbps bitrate with volume normalization  
✅ **Bluetooth Integration** - Direct output to paired speaker
✅ **Spotify Connect** - Appears in all Spotify apps
✅ **Voice Assistant Integration** - Shared OAuth tokens
✅ **Auto-discovery** - Network advertisement via Avahi/mDNS

## Files Created
- `/etc/systemd/system/librespot.service - Systemd service file
- `/home/jubers/Documents/voice_assistant/start_librespot.sh` - Manual startup script
- `/home/jubers/.cache/librespot/credentials.json` - Librespot OAuth credentials  
- `/home/jubers/Documents/voice_assistant/.cache-fh6zfkxud9q06b6j0ihhootyu` - Spotipy OAuth tokens
- `/etc/apt/sources.list.d/raspotify.list` - Package repository

## Notes
- Requires Spotify Premium account for 320kbps and Spotify Connect
- OAuth tokens refresh automatically when needed
- Librespot binary provided by Raspotify package
- Device name must match `setup.txt` for voice assistant integration


sudo systemctl daemon-reload && sudo systemctl enable librespot

sudo systemctl start librespot

sudo systemctl status librespot --