# Quick Start Guide - Centralized UI

## 🚀 Getting Started in 5 Minutes

### Step 1: Install Dependencies
```bash
cd centralized_ui
pip install -r requirements.txt
```

### Step 2: Run the Server
```bash
python app.py
```

You should see:
```
Starting Centralized UI Server on 0.0.0.0:5000
```

### Step 3: Open Dashboard
- **Local:** http://localhost:5000
- **Network:** http://YOUR_PI_IP:5000

### Step 4: Test Controls
- Toggle camera on/off
- Toggle anime face
- Try automation buttons
- Check system status

## 📋 Integration Checklist

After basic setup, integrate your modules:

### Camera Feed
- [ ] Update `app.py` line 160 with camera module
- [ ] Modify `/video_feed` route
- [ ] Test live stream

### Anime Face
- [ ] Update `app.py` line 260 with anime display module
- [ ] Modify `/anime_feed` route
- [ ] Test expression changes

### Weather
- [ ] Get API key (OpenWeatherMap or Weather API)
- [ ] Update `app.py` line 180 `get_weather()`
- [ ] Add config.ini with credentials

### Music Player
- [ ] Choose provider (Spotify, YouTube Music, etc.)
- [ ] Add credentials to config.ini
- [ ] Update `handle_music_command()` function
- [ ] Test play/pause controls

### Home Automation
- [ ] Map GPIO pins for devices
- [ ] Test relay/GPIO control
- [ ] Update device buttons in HTML if needed

### System Monitor
- [ ] Verify CPU temp sensor path
- [ ] Test on your Pi model
- [ ] Adjust thresholds in config.ini

## 🔧 Common Issues

### Dashboard shows blank page
```bash
# Check Flask is running
ps aux | grep app.py

# Check logs
python app.py  # Run in foreground to see errors
```

### Offline status indicator
```bash
# Check if SocketIO is connected
# Look in browser console (F12)
```

### Integrations not working
1. Verify modules exist: `ls ../camera/`, `ls ../connectors/`
2. Test individually: `python -c "from camera.camera_stream_simple import ..."`
3. Add try/except blocks for debugging

### Memory issues
```bash
# Check memory usage
free -h
htop  # Press 'q' to exit

# Reduce update intervals in app.py
```

## 📱 Access from Multiple Devices

### From Windows/Mac/Linux
```
http://YOUR_PI_IP:5000
```

### Find Your Pi's IP
```bash
hostname -I
```

### Access over WAN (not recommended for security)
- Use ngrok or similar tunnel
- Or setup reverse proxy with auth

## 🎨 Customize Dashboard

### Change Colors
Edit `static/css/styles.css`:
```css
:root {
    --primary-color: #YOUR_COLOR;
}
```

### Add Widget
1. Add HTML section in `templates/index.html`
2. Add CSS in `static/css/styles.css`
3. Add JS handler in `static/js/app.js`
4. Add Flask route in `app.py`

### Reorganize Layout
Modify HTML widget order in `templates/index.html`

## 🔐 Security Tips

### Change Flask Secret Key
In `app.py`:
```python
app.config['SECRET_KEY'] = 'a-very-long-random-string'
```

### Restrict Network Access
```bash
# Only allow localhost
# In app.py: host='127.0.0.1'

# Or use nginx reverse proxy with auth
```

### Use HTTPS
```bash
# Generate certificate
openssl req -x509 -newkey rsa:4096 -nodes -out cert.pem -keyout key.pem -days 365

# In app.py:
socketio.run(app, host='0.0.0.0', port=5000, ssl_context=('cert.pem', 'key.pem'))
```

## 📊 Performance Optimization

### For Low-End Pi (Pi Zero/Pi 3)
```python
# Increase update intervals in app.py
time.sleep(10)  # system status
time.sleep(30)  # weather
time.sleep(5)   # music

# Disable heavy features
# Comment out anime face integration
```

### For High-End Pi (Pi 4/Pi 5)
```python
# Decrease update intervals for responsiveness
time.sleep(2)   # system status
time.sleep(5)   # weather
time.sleep(1)   # music
```

## 📦 Backup & Restore

### Backup Configuration
```bash
cp centralized_ui/config.ini centralized_ui/config.ini.backup
```

### Backup Data
```bash
# If using database
cp -r chroma_memory/ chroma_memory.backup/
```

## 🆘 Getting Help

### View Logs
```bash
# If running with systemd
sudo journalctl -u centralized_ui -f

# If running directly
python app.py  # Shows console output
```

### Enable Debug Mode
```python
# In app.py
app.config['DEBUG'] = True
socketio.run(app, debug=True)
```

### Test Components
```bash
# Test camera
python camera_stream_simple.py

# Test weather
python -c "from connectors.weather_connector import WeatherConnector"

# Test music
python -c "from connectors.spotify_connector import SpotifyConnector"
```

## 📈 Next Steps

1. ✅ Complete integration checklist
2. ✅ Test all features
3. ✅ Setup systemd auto-start
4. ✅ Customize theme
5. ✅ Add more widgets
6. ✅ Setup network access
7. ✅ Configure backups

## 📚 Additional Resources

- Flask Documentation: https://flask.palletsprojects.com/
- SocketIO: https://python-socketio.readthedocs.io/
- CSS Grid: https://developer.mozilla.org/en-US/docs/Web/CSS/CSS_Grid_Layout
- JavaScript WebSocket: https://developer.mozilla.org/en-US/docs/Web/API/WebSocket

## 🎉 Congratulations!

Your centralized UI is now running! Customize it to match your Voice Assistant setup.

Need help? Check the README.md for detailed documentation.
