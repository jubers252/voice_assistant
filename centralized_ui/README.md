# 🎙️ Centralized UI Dashboard

A unified web-based dashboard for your Voice Assistant Raspberry Pi, displaying camera feed, anime face, weather, music player, and home automation controls in a single-column responsive layout.

## Features

✨ **Single-Column Layout** - All features stacked vertically for easy scrolling
📹 **Camera Feed** - Live video stream from your camera
✨ **Anime Face Display** - Dynamic anime character responses
🌤️ **Weather & Time** - Real-time weather and clock display
🎵 **Music Player** - Full-featured music player with playlist
🏠 **Home Automation** - Control lights, fan, AC, doorbell
📊 **System Monitor** - CPU, memory, and temperature status

## Installation

### 1. Install Dependencies

```bash
cd /home/pi/Documents/voice_assistant/centralized_ui
pip install -r requirements.txt
```

### 2. Run the Server

```bash
python app.py
```

The dashboard will be available at `http://localhost:5000`

### 3. Setup for Network Access

Access from any device on your network:
- Replace `localhost` with your Raspberry Pi's IP address
- Example: `http://192.168.1.100:5000`

### 4. (Optional) Setup Auto-Start with Systemd

Copy the service file to systemd:
```bash
sudo cp centralized_ui.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable centralized_ui
sudo systemctl start centralized_ui
```

Check status:
```bash
sudo systemctl status centralized_ui
```

View logs:
```bash
sudo journalctl -u centralized_ui -f
```

## File Structure

```
centralized_ui/
├── app.py                 # Flask backend server
├── requirements.txt       # Python dependencies
├── templates/
│   └── index.html        # Main dashboard HTML
├── static/
│   ├── css/
│   │   └── styles.css    # Main stylesheet
│   └── js/
│       └── app.js        # Frontend JavaScript
└── README.md             # This file
```

## Integration Guide

### Camera Feed
Update `app.py` line ~160 in `video_feed()`:
```python
from camera.camera_stream_simple import start_stream
# Integrate camera streaming
```

### Weather Data
Update `app.py` line ~180 in `get_weather()`:
```python
from connectors.weather_connector import WeatherConnector
weather = WeatherConnector()
```

### Music Player
Update `app.py` line ~200 in `handle_music_command()`:
```python
from connectors.spotify_connector import SpotifyConnector
# or youtube_api, yt_music
```

### Home Automation
Update `app.py` line ~280 in `handle_device_command()`:
```python
from connectors.home_automation import HomeAutomation
automation = HomeAutomation()
```

### Anime Face
Update `app.py` line ~260 in `handle_anime_face_command()`:
```python
from anime_face_display import AnimeFaceDisplay
anime = AnimeFaceDisplay()
```

## API Endpoints

### REST Endpoints
- `GET /` - Main dashboard
- `GET /api/weather` - Current weather
- `GET /api/playlist` - Music playlist
- `GET /api/system_status` - System resources
- `POST /api/command` - Send commands

### WebSocket Events
- `connect` - Client connected
- `disconnect` - Client disconnected
- `command` - Receive commands
- `system_status` - System updates
- `weather_update` - Weather updates
- `music_update` - Music player updates
- `device_status` - Device state updates

## WebSocket Message Format

### Commands from Frontend to Backend
```json
{
  "type": "camera|anime_face|music|device",
  "payload": {
    "action": "start|stop|play|pause|etc",
    "value": "optional value"
  }
}
```

### Updates from Backend to Frontend
```json
{
  "type": "system_status|weather_update|music_update|device_status",
  "payload": { /* ... */ }
}
```

## Configuration

### Change Flask Secret Key
In `app.py` line ~30:
```python
app.config['SECRET_KEY'] = 'your-secure-secret-key-here'
```

### Change Port
In `app.py` line ~284:
```python
socketio.run(app, host='0.0.0.0', port=8080, debug=False)
```

### System Update Intervals
- Weather: 10 minutes (line ~232)
- Music: 2 seconds (line ~244)
- System Stats: 5 seconds (line ~220)

## Customization

### Modify Theme Colors
Edit `/static/css/styles.css` root variables:
```css
:root {
    --primary-color: #6366f1;
    --secondary-color: #8b5cf6;
    /* ... */
}
```

### Add New Widgets
1. Add HTML in `templates/index.html`
2. Add CSS in `static/css/styles.css`
3. Add JavaScript handlers in `static/js/app.js`
4. Add backend routes in `app.py`

## Troubleshooting

### Dashboard doesn't load
- Check if Flask server is running: `ps aux | grep app.py`
- Check firewall: `sudo ufw status`
- Check logs: `sudo journalctl -u centralized_ui -f`

### WebSocket connection fails
- Check if SocketIO is running
- Verify firewall allows WebSocket traffic (port 5000)
- Check browser console for errors (F12)

### Camera/Music not working
- Verify integrations are implemented in `app.py`
- Check console logs for integration errors
- Test individual modules separately

### Memory/CPU high
- Adjust update intervals (weather, music, system status)
- Reduce camera stream quality
- Check for background processes

## Performance Tips

1. **For Older Raspberry Pi:**
   - Disable anime face display
   - Reduce camera FPS
   - Increase update intervals

2. **For Better Responsiveness:**
   - Use Ethernet instead of WiFi
   - Run close to router
   - Disable heavy integrations

3. **For Multiple Users:**
   - Use reverse proxy (nginx)
   - Increase socketio backlog
   - Add load balancing

## Browser Compatibility

- Chrome/Chromium ✅
- Firefox ✅
- Safari ✅
- Edge ✅
- Mobile browsers ✅ (responsive design)

## License

Part of Voice Assistant project

## Support

For issues or questions:
1. Check the logs: `sudo journalctl -u centralized_ui`
2. Verify all integrations in `app.py`
3. Test individual components separately
4. Check Raspberry Pi resources: `free -h`, `htop`
