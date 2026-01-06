#!/bin/bash
# Installation script for Voice Assistant service

echo "Installing Voice Assistant service..."

# Copy service file to systemd directory
sudo cp voice_assistant.service /etc/systemd/system/

# Reload systemd to recognize the new service
sudo systemctl daemon-reload

# Enable the service to start on boot
sudo systemctl enable voice_assistant.service

echo "Service installed successfully!"
echo ""
echo "Available commands:"
echo "  Start service:   sudo systemctl start voice_assistant"
echo "  Stop service:    sudo systemctl stop voice_assistant"
echo "  Restart service: sudo systemctl restart voice_assistant"
echo "  View status:     sudo systemctl status voice_assistant"
echo "  View logs:       sudo journalctl -u voice_assistant -f"
echo "  Disable service: sudo systemctl disable voice_assistant"
echo "  Enable service:  sudo systemctl enable voice_assistant"
