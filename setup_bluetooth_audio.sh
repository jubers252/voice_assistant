#!/bin/bash
# Spotify Connect + Bluetooth A# Stop Spotify Connect service
stop_spotify_service() {
    systemctl --user stop librespot.service
}etup for# Disable system raspotify service (if installed)
disable_system_raspotify() {
    sudo systemctl stop raspotify 2>/dev/null || true
    sudo systemctl disable raspotify 2>/dev/null || true
}rry Pi 5
# Simple functions to setup and manage Spotify Connect with Bluetooth

# Configuration
BLUETOOTH_MAC="7D:80:26:0A:FA:00"
BLUETOOTH_SINK="bluez_output.7D_80_26_0A_FA_00.1"
DEVICE_NAME="RaspberryPi5-Sofi"

# Install librespot binary via Raspotify package
install_librespot() {
    curl -sL https://dtcooper.github.io/raspotify/install.sh | sh
}

# Create user systemd service for librespot
create_spotify_service() {
    mkdir -p ~/.config/systemd/user
    
    cat > ~/.config/systemd/user/librespot.service << 'EOF'
[Unit]
Description=Librespot (Spotify Connect Client) - User Service
After=pipewire.service

[Service]
Type=simple
ExecStart=/usr/bin/librespot --name "RaspberryPi5-Sofi" --device-type computer --bitrate 160 --initial-volume 70 --enable-volume-normalisation --backend pulseaudio --device "bluez_output.7D_80_26_0A_FA_00.1"
Restart=always
RestartSec=5

[Install]
WantedBy=default.target
EOF

    systemctl --user daemon-reload
    systemctl --user enable librespot.service
    loginctl enable-linger $USER
}

# Start Spotify Connect service
start_spotify_service() {
    systemctl --user start librespot.service
}

# Stop Spotify Connect service
stop_spotify_service() {
    echo "� Stopping Spotify Connect service..."
    systemctl --user stop librespot.service
    echo "✅ Service stopped"
}

# Restart Spotify Connect service
restart_spotify_service() {
    systemctl --user restart librespot.service
}

# Disable system raspotify service (if installed)
disable_system_raspotify() {
    echo "� Disabling system raspotify service..."
    sudo systemctl stop raspotify 2>/dev/null || true
    sudo systemctl disable raspotify 2>/dev/null || true
    echo "✅ System service disabled"
}

# Change to different Bluetooth speaker
change_bluetooth_speaker() {
    if [ -z "$1" ]; then
        return 1
    fi
    
    local new_device="$1"
    sed -i "s/--device \".*\"/--device \"$new_device\"/" ~/.config/systemd/user/librespot.service
    systemctl --user daemon-reload
    systemctl --user restart librespot.service
}

# Change to HDMI audio
change_to_hdmi() {
    sed -i 's/--device ".*"/--device "hw:0,0"/' ~/.config/systemd/user/librespot.service
    sed -i 's/--backend pulseaudio/--backend alsa/' ~/.config/systemd/user/librespot.service
    systemctl --user daemon-reload
    systemctl --user restart librespot.service
}

# Change to USB audio
change_to_usb() {
    sed -i 's/--device ".*"/--device "hw:2,0"/' ~/.config/systemd/user/librespot.service
    sed -i 's/--backend pulseaudio/--backend alsa/' ~/.config/systemd/user/librespot.service
    systemctl --user daemon-reload
    systemctl --user restart librespot.service
}

# Check service status
check_status() {
    systemctl --user status librespot.service --no-pager
}

# List available audio devices
list_audio_devices() {
    bluetoothctl devices Connected
    pactl list sinks short
    cat /proc/asound/cards
}

# Test audio output
test_audio() {
    paplay /usr/share/sounds/alsa/Front_Left.wav 2>/dev/null
}

# Complete setup - run everything
complete_setup() {
    install_librespot
    disable_system_raspotify
    create_spotify_service
    start_spotify_service
}# Show available functions
show_help() {
    # Available functions:
    # complete_setup, install_librespot, create_spotify_service
    # start_spotify_service, stop_spotify_service, restart_spotify_service
    # check_status, change_bluetooth_speaker, change_to_hdmi, change_to_usb
    # list_audio_devices, test_audio
    return 0
}

# LEGACY: Original Bluetooth connection script
connect_bluetooth_legacy() {
    # Check if already connected
    if ! bluetoothctl info $BLUETOOTH_MAC | grep -q "Connected: yes"; then
        bluetoothctl connect $BLUETOOTH_MAC
        sleep 2
    fi
    
    # Set as default audio sink
    pactl set-default-sink $BLUETOOTH_SINK
    
    # Test audio
    paplay --device=$BLUETOOTH_SINK /usr/share/sounds/alsa/Front_Left.wav 2>/dev/null
    
    # Restart Raspotify
    sudo systemctl restart raspotify
}