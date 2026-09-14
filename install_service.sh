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

# Close/stop the dashboard (if ever needed)
sudo systemctl stop centralized_ui.service

# Start it again
sudo systemctl start centralized_ui.service

# Check status
sudo systemctl status centralized_ui.service

# View logs
sudo journalctl -u centralized_ui.service -f
