📁 Centralized UI Project Structure
=====================================

centralized_ui/
│
├── 📄 app.py                      # Main Flask backend server
├── 📄 integrations.py             # Integration helpers for Voice Assistant modules
├── 📄 requirements.txt            # Python dependencies
├── 📄 centralized_ui.service      # Systemd service file for auto-start
│
├── 📁 templates/
│   └── 📄 index.html              # Main HTML dashboard
│
├── 📁 static/
│   ├── 📁 css/
│   │   └── 📄 styles.css          # Main stylesheet (dark theme)
│   │
│   └── 📁 js/
│       └── 📄 app.js              # Frontend JavaScript
│
├── 📚 Documentation/
│   ├── 📄 README.md               # Full documentation
│   ├── 📄 QUICKSTART.md           # Quick start guide
│   └── 📄 FOLDER_STRUCTURE.md     # This file
│
└── 📝 Configuration/
    ├── 📄 config.ini.example      # Configuration template
    └── 📄 .gitignore              # Git ignore file


FEATURES OVERVIEW
=================

Dashboard Sections (Single Column Layout):

1. 📹 Camera Feed
   - Live video stream from camera
   - Start/stop controls
   - Status indicator

2. ✨ Anime Face Display
   - Dynamic anime character
   - Emotion detection
   - Start/stop controls

3. 🌤️ Weather & Time
   - Current time (24-hour)
   - Temperature display
   - Humidity percentage
   - Weather description

4. 🎵 Music Player
   - Album artwork
   - Track information
   - Play/pause/next/previous
   - Progress bar
   - Volume control
   - Playlist viewer

5. 🏠 Home Automation
   - Light control
   - Fan control
   - AC control
   - Doorbell/security

6. 📊 System Status
   - CPU usage
   - Memory usage
   - CPU temperature
   - Real-time monitoring


FILE DESCRIPTIONS
=================

Backend (Python):
-----------------

app.py
  - Flask web server
  - REST API endpoints
  - WebSocket handlers
  - Command processing
  - Background update threads
  - Error handling

integrations.py
  - Camera integration helper
  - Weather integration helper
  - Music integration helper
  - Home automation helper
  - Anime face integration helper
  - Integration manager class


Frontend (HTML/CSS/JavaScript):
-------------------------------

templates/index.html
  - HTML structure
  - Bootstrap section divs
  - Form inputs
  - List containers
  - Script references

static/css/styles.css
  - Dark theme variables
  - Responsive layout
  - Component styling
  - Animation keyframes
  - Mobile breakpoints

static/js/app.js
  - DashboardManager class
  - WebSocket initialization
  - Event listeners
  - API calls
  - Real-time updates
  - UI state management


Configuration & Setup:
---------------------

requirements.txt
  - Flask==2.3.3
  - Flask-CORS==4.0.0
  - Flask-SocketIO==5.3.5
  - python-socketio==5.9.0
  - python-engineio==4.7.1
  - psutil==5.9.5

config.ini.example
  - Server settings
  - Camera configuration
  - Weather API keys
  - Music provider credentials
  - GPIO pin mappings
  - Logging configuration

centralized_ui.service
  - Systemd service unit
  - Auto-start on boot
  - Process management
  - Resource limits
  - Security options

.gitignore
  - Python cache files
  - IDE files
  - Log files
  - Environment variables
  - Credentials
  - Temporary files


Documentation:
--------------

README.md
  - Full feature overview
  - Installation steps
  - Integration guide
  - API documentation
  - Customization guide
  - Troubleshooting

QUICKSTART.md
  - 5-minute setup
  - Integration checklist
  - Common issues
  - Security tips
  - Performance optimization

FOLDER_STRUCTURE.md
  - Project layout (this file)
  - File descriptions
  - Technology stack
  - Architecture overview


TECHNOLOGY STACK
================

Backend:
- Python 3.7+
- Flask (web framework)
- Flask-SocketIO (WebSocket)
- psutil (system monitoring)

Frontend:
- HTML5
- CSS3 (Grid, Flexbox, Variables)
- JavaScript (ES6+)
- WebSocket API

Server:
- HTTP for REST API
- WebSocket for real-time updates

Design:
- Responsive (mobile to desktop)
- Dark theme
- Single-column layout
- Tailored for Raspberry Pi display


ARCHITECTURE OVERVIEW
=====================

┌─────────────────────────────────────────────────────┐
│         Raspberry Pi (Backend)                      │
│                                                     │
│  ┌────────────────────────────────────────────┐   │
│  │  Flask App (app.py)                        │   │
│  ├────────────────────────────────────────────┤   │
│  │  - HTTP Server (Port 5000)                 │   │
│  │  - WebSocket Handler                       │   │
│  │  - API Routes                              │   │
│  │  - Background Tasks                        │   │
│  └────────────────────────────────────────────┘   │
│           ↓         ↓         ↓         ↓          │
│  ┌──────────┬─────────┬──────────┬──────────┐     │
│  │ Camera   │ Weather │ Music    │ GPIO     │     │
│  │ Module   │ API     │ Provider │ Control  │     │
│  └──────────┴─────────┴──────────┴──────────┘     │
│                                                     │
└─────────────────────────────────────────────────────┘
               ↕ HTTP + WebSocket
┌─────────────────────────────────────────────────────┐
│     Client Browser (Web UI)                         │
│                                                     │
│  ┌────────────────────────────────────────────┐   │
│  │  index.html (Dashboard Structure)          │   │
│  ├────────────────────────────────────────────┤   │
│  │  ┌──────────────────────────────────────┐ │   │
│  │  │  Header (Status Indicator)           │ │   │
│  │  ├──────────────────────────────────────┤ │   │
│  │  │  Camera Feed Widget                  │ │   │
│  │  ├──────────────────────────────────────┤ │   │
│  │  │  Anime Face Widget                   │ │   │
│  │  ├──────────────────────────────────────┤ │   │
│  │  │  Weather & Time Widget               │ │   │
│  │  ├──────────────────────────────────────┤ │   │
│  │  │  Music Player Widget                 │ │   │
│  │  ├──────────────────────────────────────┤ │   │
│  │  │  Home Automation Widget              │ │   │
│  │  ├──────────────────────────────────────┤ │   │
│  │  │  System Status Widget                │ │   │
│  │  ├──────────────────────────────────────┤ │   │
│  │  │  Footer (Last Update Time)           │ │   │
│  │  └──────────────────────────────────────┘ │   │
│  │                                            │   │
│  │  styles.css (Visual Styling)              │   │
│  │  app.js (Interactions & Updates)          │   │
│  └────────────────────────────────────────────┘   │
│                                                     │
└─────────────────────────────────────────────────────┘


DATA FLOW
=========

1. Page Load:
   Browser → app.py:/ → index.html → Load CSS/JS

2. WebSocket Connection:
   Browser → app.py:/ws → Persistent connection
   
3. Real-time Updates:
   Backend threads → app.py → WebSocket → Browser → UI Update
   
4. User Interaction:
   Browser UI → JavaScript → WebSocket → app.py → Action
   
5. API Polling (Fallback):
   Browser UI → JavaScript → HTTP POST → app.py → Response


DEPLOYMENT LOCATIONS
====================

Development:
  Local: http://localhost:5000
  Network: http://<pi-ip>:5000

Production:
  Behind nginx reverse proxy
  HTTPS enabled
  Authentication added
  Rate limiting configured


EXTENSION POINTS
================

Add Camera Feed:
  1. Implement camera streaming in app.py
  2. Update /video_feed route
  3. Modify camera-feed img src

Add Music Control:
  1. Initialize music provider in integrations.py
  2. Implement handle_music_command()
  3. Add trackbar and volume controls (already present)

Add Weather Data:
  1. Get weather API key
  2. Initialize in integrations.py
  3. Update get_weather() route

Add Home Automation:
  1. Map GPIO pins in config
  2. Initialize in integrations.py
  3. Implement GPIO control

Add Custom Widget:
  1. Add HTML section in index.html
  2. Add CSS styling in styles.css
  3. Add JavaScript handler in app.js
  4. Add Flask route in app.py


PERFORMANCE CONSIDERATIONS
===========================

Memory:
  - Flask: ~50-100 MB
  - SocketIO: ~20-30 MB
  - Threads: ~10 MB each
  - Typical: ~150-200 MB base

CPU:
  - Idle: <2%
  - Active streaming: 10-30%
  - High load: Can spike to 80%+

Network:
  - WebSocket: Continuous connection
  - HTTP: ~1-5 KB per request
  - Stream: Variable (camera dependent)

Optimization:
  - Reduce update frequencies
  - Disable unused features
  - Use connection pooling
  - Cache static assets


VERSION HISTORY
===============

v1.0 (Initial Release)
  - Single-column dashboard layout
  - 6 main widgets
  - Real-time WebSocket updates
  - Responsive design
  - Integration helpers
  - Systemd service
  - Documentation


FUTURE ENHANCEMENTS
===================

- [ ] Multi-column layout option
- [ ] Dark/Light theme toggle
- [ ] Voice control integration
- [ ] Notification system
- [ ] Database for history
- [ ] Advanced graphs
- [ ] Mobile app
- [ ] Voice commands
- [ ] Gesture recognition
- [ ] Machine learning features
