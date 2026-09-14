"""
Centralized UI Flask Backend
Handles camera feed, anime face, weather, music player, and home automation
"""

import os
import json
import time
import psutil
import signal
import subprocess
import threading
import sys
from datetime import datetime
from flask import Flask, render_template, jsonify, request, redirect
from flask_cors import CORS
from flask_socketio import SocketIO, emit, disconnect
import logging

# Add parent directory to path for imports
PARENT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PARENT_DIR)
VOICE_ASSISTANT_SCRIPT = os.path.join(PARENT_DIR, 'voice_assistant.py')

# Import weather connector
try:
    from connectors.weather_connector import WeatherAPIConnector
    weather_connector = WeatherAPIConnector()
    weather_available = True
except Exception as e:
    print(f"Warning: Weather connector not available: {e}")
    weather_available = False

# Initialize Flask app
app = Flask(__name__, 
    template_folder='templates',
    static_folder='static',
    static_url_path='/static'
)
app.config['SECRET_KEY'] = 'your-secret-key-here-change-in-production'

CORS(app)
socketio = SocketIO(app, cors_allowed_origins="*")

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ============================================
# GLOBAL STATE
# ============================================

class GlobalState:
    def __init__(self):
        self.camera_active = False
        self.anime_face_active = False
        self.music_playing = False
        self.current_track = 0
        self.devices = {
            'light': False,
            'fan': False,
            'ac': False,
            'doorbell': True  # armed by default
        }
        self.weather_data = {}
        self.system_status = {}
        self.assistant_process = None  # Popen handle, only set if we launched it ourselves

state = GlobalState()

def _launch_browser():
    """Launch Chromium browser in kiosk mode (runs in background thread)"""
    try:
        # Wait a bit for the server to be ready
        time.sleep(2)
        
        # Set environment variables
        env = os.environ.copy()
        env['DISPLAY'] = ':0'
        env['XAUTHORITY'] = '/home/pi/.Xauthority'
        
        # Try different browser names
        browsers = ['chromium-browser', 'chromium', 'google-chrome']
        browser_cmd = None
        
        for browser in browsers:
            if subprocess.run(['which', browser], capture_output=True).returncode == 0:
                browser_cmd = browser
                break
        
        if not browser_cmd:
            logger.warning("No browser found. Skipping auto-launch.")
            return
        
        logger.info(f"Launching browser with {browser_cmd}...")
        
        # Launch browser in kiosk mode
        subprocess.Popen([
            browser_cmd,
            '--kiosk',
            '--start-fullscreen',
            '--noerrdialogs',
            '--disable-infobars',
            '--no-first-run',
            '--disable-session-crashed-bubble',
            '--disable-translate',
            '--check-for-update-interval=31536000',
            '--overscroll-history-navigation=0',
            'http://localhost:5000'
        ], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        
        logger.info("Browser launched in background")
    except Exception as e:
        logger.warning(f"Failed to launch browser: {e}")

def _find_assistant_pid():
    """Find a running voice_assistant.py process, however it was started."""
    for proc in psutil.process_iter(['pid', 'cmdline']):
        try:
            cmdline = proc.info['cmdline'] or []
            if any('voice_assistant.py' in part for part in cmdline):
                return proc.info['pid']
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return None

# ============================================
# ROUTES
# ============================================

@app.route('/')
def index():
    """Serve the main dashboard"""
    return render_template('index.html')

@app.route('/video_feed')
def video_feed():
    """Stream camera feed"""
    # This is a placeholder - integrate with your camera_stream_simple.py
    # For now, return a placeholder image
    return redirect('/static/placeholder.jpg')

@app.route('/anime_feed')
def anime_feed():
    """Stream anime face"""
    # This is a placeholder - integrate with your anime_face_display.py
    return redirect('/static/placeholder.jpg')

# ============================================
# API ENDPOINTS
# ============================================

@app.route('/api/weather', methods=['GET'])
def get_weather():
    """Get current weather data"""
    try:
        location = request.args.get('location', 'Pune')  # Default to Pune
        
        if weather_available:
            # Get real weather from API
            weather_data = weather_connector.get_current_weather(location, aqi=False)
            
            # Extract relevant fields for the UI
            if 'current' in weather_data:
                current = weather_data['current']
                return jsonify({
                    'temperature': current.get('temp_c', 0),
                    'humidity': current.get('humidity', 0),
                    'condition': current.get('condition', {}).get('text', 'Unknown'),
                    'description': current.get('condition', {}).get('text', 'No description'),
                    'wind_speed': current.get('wind_kph', 0),
                    'pressure': current.get('pressure_mb', 0),
                    'location': location,
                    'timestamp': datetime.now().isoformat()
                })
            else:
                raise Exception("Invalid weather API response")
        else:
            # Fallback to placeholder data
            return jsonify({
                'temperature': 28.5,
                'humidity': 65,
                'condition': 'Partly Cloudy',
                'description': 'Warm and humid with occasional clouds',
                'wind_speed': 12,
                'pressure': 1013,
                'location': location,
                'timestamp': datetime.now().isoformat()
            })
    except Exception as e:
        logger.error(f"Weather error: {e}")
        return jsonify({
            'error': str(e),
            'temperature': 0,
            'humidity': 0,
            'condition': 'Error',
            'description': 'Unable to fetch weather data'
        }), 500

@app.route('/api/playlist', methods=['GET'])
def get_playlist():
    """Get current playlist"""
    try:
        # TODO: Integrate with music connectors (spotify, youtube_api, yt_music)
        playlist = {
            'tracks': [
                {'title': 'Track 1', 'artist': 'Artist 1'},
                {'title': 'Track 2', 'artist': 'Artist 2'},
                {'title': 'Track 3', 'artist': 'Artist 3'},
            ]
        }
        return jsonify(playlist)
    except Exception as e:
        logger.error(f"Playlist error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/system_status', methods=['GET'])
def get_system_status():
    """Get system resource usage"""
    try:
        # Get CPU usage
        cpu_percent = psutil.cpu_percent(interval=1)
        
        # Get memory usage
        memory = psutil.virtual_memory()
        memory_percent = memory.percent
        
        # Get temperature (Raspberry Pi specific)
        temperature = get_cpu_temperature()
        
        status = {
            'cpu_usage': cpu_percent,
            'memory_usage': memory_percent,
            'temperature': temperature,
            'timestamp': datetime.now().isoformat()
        }
        
        state.system_status = status
        return jsonify(status)
    except Exception as e:
        logger.error(f"System status error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/command', methods=['POST'])
def handle_command():
    """Handle commands from frontend"""
    try:
        data = request.get_json()
        command_type = data.get('type')
        payload = data.get('payload', {})
        
        if command_type == 'camera':
            handle_camera_command(payload)
        elif command_type == 'anime_face':
            handle_anime_face_command(payload)
        elif command_type == 'music':
            handle_music_command(payload)
        elif command_type == 'device':
            handle_device_command(payload)
        
        return jsonify({'success': True})
    except Exception as e:
        logger.error(f"Command error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/switch_tab', methods=['POST'])
def switch_tab():
    """Switch to a specific tab (triggered by voice assistant)"""
    try:
        data = request.get_json()
        tab = data.get('tab')
        
        valid_tabs = ['camera', 'anime', 'weather', 'music', 'automation', 'system']
        
        if tab not in valid_tabs:
            return jsonify({'error': f'Invalid tab. Must be one of: {valid_tabs}'}), 400
        
        logger.info(f"[UI] Switching to tab: {tab}")
        
        # Emit to all connected clients to switch tab
        # Use namespace='/' to ensure proper broadcasting from HTTP route context
        socketio.emit('switch_tab', {'tab': tab}, namespace='/')
        
        logger.info(f"[UI] Switch tab event emitted for: {tab}")
        
        return jsonify({'success': True, 'tab': tab})
    except Exception as e:
        logger.error(f"[UI] Tab switch error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/assistant/status', methods=['GET'])
def assistant_status():
    """Report whether voice_assistant.py is currently running."""
    pid = _find_assistant_pid()
    return jsonify({'running': pid is not None, 'pid': pid})

@app.route('/api/assistant/start', methods=['POST'])
def assistant_start():
    """Launch voice_assistant.py from the dashboard's Start button."""
    try:
        existing_pid = _find_assistant_pid()
        if existing_pid:
            return jsonify({'success': True, 'message': 'Already running', 'pid': existing_pid})

        # Prepare environment with audio support
        env = os.environ.copy()
        # Set ALSA device to ReSpeaker (card 2 from aplay -l output)
        env['ALSA_CARD'] = 'Lite'
        # Ensure we have home directory for ALSA config
        env['HOME'] = '/home/pi'
        # Set user for audio permissions
        env['USER'] = 'pi'
        # PulseAudio environment variables are inherited from os.environ.copy()
        
        # Open log files for debugging
        log_file = open('/tmp/voice_assistant.log', 'a')
        
        state.assistant_process = subprocess.Popen(
            [sys.executable, VOICE_ASSISTANT_SCRIPT],
            cwd=PARENT_DIR,
            env=env,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            start_new_session=True
        )
        logger.info(f"[ASSISTANT] Started voice_assistant.py (PID: {state.assistant_process.pid}) - logging to /tmp/voice_assistant.log")
        return jsonify({'success': True, 'pid': state.assistant_process.pid})
    except Exception as e:
        logger.error(f"[ASSISTANT] Start error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/assistant/stop', methods=['POST'])
def assistant_stop():
    """Gracefully stop voice_assistant.py from the dashboard's Stop button."""
    try:
        pid = _find_assistant_pid()
        if not pid:
            return jsonify({'success': True, 'message': 'Not running'})

        logger.info(f"[ASSISTANT] Stopping voice_assistant.py (PID: {pid})")

        def _terminate(target_pid):
            time.sleep(0.3)  # let the HTTP response flush before the signal is sent
            try:
                os.kill(target_pid, signal.SIGTERM)
            except ProcessLookupError:
                pass

        threading.Thread(target=_terminate, args=(pid,), daemon=True).start()

        return jsonify({'success': True, 'message': 'Stopping...'})
    except Exception as e:
        logger.error(f"[ASSISTANT] Stop error: {e}")
        return jsonify({'error': str(e)}), 500

# ============================================
# WEBSOCKET HANDLERS
# ============================================

@socketio.on('connect')
def handle_connect():
    """Handle client connection"""
    logger.info('Client connected')
    emit('response', {'data': 'Connected to server'})

@socketio.on('disconnect')
def handle_disconnect():
    """Handle client disconnection"""
    logger.info('Client disconnected')

@socketio.on('command')
def handle_socket_command(data):
    """Handle commands via WebSocket"""
    try:
        command_type = data.get('type')
        payload = data.get('payload', {})
        
        if command_type == 'camera':
            handle_camera_command(payload)
        elif command_type == 'anime_face':
            handle_anime_face_command(payload)
        elif command_type == 'music':
            handle_music_command(payload)
        elif command_type == 'device':
            handle_device_command(payload)
        
        emit('response', {'success': True})
    except Exception as e:
        logger.error(f"Socket command error: {e}")
        emit('error', {'message': str(e)})

# ============================================
# COMMAND HANDLERS
# ============================================

def handle_camera_command(payload):
    """Handle camera control commands"""
    action = payload.get('action')
    
    if action == 'start':
        state.camera_active = True
        logger.info("Camera started")
        # TODO: Integrate with camera module
    elif action == 'stop':
        state.camera_active = False
        logger.info("Camera stopped")
        # TODO: Integrate with camera module
    
    # Broadcast update
    socketio.emit('device_status', {'device': 'camera', 'status': state.camera_active})

def handle_anime_face_command(payload):
    """Handle anime face control commands"""
    action = payload.get('action')
    
    if action == 'start':
        state.anime_face_active = True
        logger.info("Anime face started")
        # TODO: Integrate with anime face module
    elif action == 'stop':
        state.anime_face_active = False
        logger.info("Anime face stopped")
        # TODO: Integrate with anime face module
    
    # Broadcast update
    socketio.emit('device_status', {'device': 'anime_face', 'status': state.anime_face_active})

def handle_music_command(payload):
    """Handle music player commands"""
    action = payload.get('action')
    
    if action == 'play':
        state.music_playing = True
        logger.info("Music playing")
        # TODO: Integrate with music connectors
    elif action == 'pause':
        state.music_playing = False
        logger.info("Music paused")
        # TODO: Integrate with music connectors
    elif action == 'next':
        logger.info("Next track")
        # TODO: Integrate with music connectors
    elif action == 'previous':
        logger.info("Previous track")
        # TODO: Integrate with music connectors
    elif action == 'volume':
        volume = payload.get('value', 70)
        logger.info(f"Volume set to {volume}%")
        # TODO: Integrate with volume control
    elif action == 'seek':
        position = payload.get('value', 0)
        logger.info(f"Seek to {position}")
        # TODO: Integrate with music player
    
    # Broadcast update
    socketio.emit('music_update', {
        'title': 'Example Track',
        'artist': 'Example Artist',
        'is_playing': state.music_playing,
        'progress': 0,
        'duration': 180
    })

def handle_device_command(payload):
    """Handle home automation device commands"""
    device = payload.get('device')
    action = payload.get('action')
    
    if device in state.devices:
        state.devices[device] = (action == 'on')
        logger.info(f"Device {device} turned {action}")
        # TODO: Integrate with GPIO/relay control
        
        # Broadcast update
        socketio.emit('device_status', {
            'device': device,
            'status': action
        })

# ============================================
# UTILITY FUNCTIONS
# ============================================

def get_cpu_temperature():
    """Get CPU temperature for Raspberry Pi"""
    try:
        with open('/sys/class/thermal/thermal_zone0/temp', 'r') as f:
            temp_raw = f.read()
            # Temperature is in millidegrees Celsius
            temp_celsius = int(temp_raw) / 1000.0
            return round(temp_celsius, 1)
    except FileNotFoundError:
        # Not on Raspberry Pi or file not found
        return 0
    except Exception as e:
        logger.warning(f"Could not read CPU temperature: {e}")
        return 0

# ============================================
# BACKGROUND TASKS
# ============================================

def broadcast_system_status():
    """Periodically broadcast system status"""
    while True:
        try:
            cpu_percent = psutil.cpu_percent(interval=1)
            memory = psutil.virtual_memory()
            temperature = get_cpu_temperature()
            
            status = {
                'cpu_usage': cpu_percent,
                'memory_usage': memory.percent,
                'temperature': temperature
            }
            
            state.system_status = status
            socketio.emit('system_status', status)
        except Exception as e:
            logger.error(f"Error broadcasting system status: {e}")
        
        time.sleep(5)  # Update every 5 seconds

def broadcast_weather_updates():
    """Periodically broadcast weather updates"""
    while True:
        try:
            # TODO: Integrate with weather_connector.py
            weather_data = {
                'temperature': 28.5,
                'humidity': 65,
                'condition': 'Partly Cloudy',
                'description': 'Warm and humid with occasional clouds'
            }
            state.weather_data = weather_data
            socketio.emit('weather_update', weather_data)
        except Exception as e:
            logger.error(f"Error broadcasting weather: {e}")
        
        time.sleep(600)  # Update every 10 minutes

def broadcast_music_updates():
    """Periodically broadcast music player updates"""
    while True:
        try:
            # TODO: Integrate with music connectors
            music_data = {
                'title': 'Example Track',
                'artist': 'Example Artist',
                'album_art': '/static/placeholder.jpg',
                'is_playing': state.music_playing,
                'progress': 30,
                'duration': 180
            }
            socketio.emit('music_update', music_data)
        except Exception as e:
            logger.error(f"Error broadcasting music: {e}")
        
        time.sleep(2)  # Update every 2 seconds

# ============================================
# ERROR HANDLERS
# ============================================

@app.errorhandler(404)
def not_found(error):
    return jsonify({'error': 'Not found'}), 404

@app.errorhandler(500)
def internal_error(error):
    logger.error(f"Internal error: {error}")
    return jsonify({'error': 'Internal server error'}), 500

# ============================================
# STARTUP
# ============================================

def start_background_threads():
    """Start background update threads"""
    threads = [
        threading.Thread(target=broadcast_system_status, daemon=True),
        threading.Thread(target=broadcast_weather_updates, daemon=True),
        threading.Thread(target=broadcast_music_updates, daemon=True),
    ]
    
    for thread in threads:
        thread.start()
    
    logger.info("Background threads started")

if __name__ == '__main__':
    try:
        # Start background update threads
        start_background_threads()
        
        # Launch browser in background thread
        browser_thread = threading.Thread(target=_launch_browser, daemon=True)
        browser_thread.start()
        
        # Run the Flask app with SocketIO
        logger.info("Starting Centralized UI Server on 0.0.0.0:5000")
        socketio.run(app, host='0.0.0.0', port=5000, debug=False, allow_unsafe_werkzeug=True)
    except KeyboardInterrupt:
        logger.info("Server shutting down")
    except Exception as e:
        logger.error(f"Server error: {e}")
