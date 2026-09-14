"""
Integration helpers for Centralized UI
Provides examples and utilities for integrating with Voice Assistant modules
"""

import sys
import os
import logging
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

logger = logging.getLogger(__name__)

# ============================================
# CAMERA INTEGRATION
# ============================================

class CameraIntegration:
    """Integrate with camera module"""
    
    def __init__(self):
        self.camera = None
        self.stream_thread = None
        
    def initialize(self):
        """Initialize camera"""
        try:
            from camera.camera_stream_simple import CameraStream
            self.camera = CameraStream()
            logger.info("Camera initialized successfully")
            return True
        except ImportError as e:
            logger.warning(f"Camera module not found: {e}")
            return False
        except Exception as e:
            logger.error(f"Camera initialization error: {e}")
            return False
    
    def start_stream(self):
        """Start camera stream"""
        try:
            if self.camera:
                self.camera.start()
                logger.info("Camera stream started")
                return True
        except Exception as e:
            logger.error(f"Camera start error: {e}")
            return False
    
    def stop_stream(self):
        """Stop camera stream"""
        try:
            if self.camera:
                self.camera.stop()
                logger.info("Camera stream stopped")
                return True
        except Exception as e:
            logger.error(f"Camera stop error: {e}")
            return False
    
    def get_frame(self):
        """Get current frame"""
        try:
            if self.camera:
                return self.camera.get_frame()
        except Exception as e:
            logger.error(f"Camera frame error: {e}")
            return None


# ============================================
# WEATHER INTEGRATION
# ============================================

class WeatherIntegration:
    """Integrate with weather module"""
    
    def __init__(self):
        self.weather = None
        
    def initialize(self):
        """Initialize weather connector"""
        try:
            from connectors.weather_connector import WeatherConnector
            self.weather = WeatherConnector()
            logger.info("Weather connector initialized")
            return True
        except ImportError as e:
            logger.warning(f"Weather module not found: {e}")
            return False
        except Exception as e:
            logger.error(f"Weather initialization error: {e}")
            return False
    
    def get_current_weather(self):
        """Get current weather data"""
        try:
            if self.weather:
                data = self.weather.get_current()
                return {
                    'temperature': data.get('temperature', 0),
                    'humidity': data.get('humidity', 0),
                    'condition': data.get('condition', 'Unknown'),
                    'description': data.get('description', 'N/A'),
                    'wind_speed': data.get('wind_speed', 0),
                    'pressure': data.get('pressure', 0),
                }
        except Exception as e:
            logger.error(f"Weather fetch error: {e}")
        
        return {
            'temperature': 0,
            'humidity': 0,
            'condition': 'Error',
            'description': 'Failed to fetch weather'
        }


# ============================================
# MUSIC INTEGRATION
# ============================================

class MusicIntegration:
    """Integrate with music connectors"""
    
    def __init__(self):
        self.spotify = None
        self.youtube = None
        self.current_provider = None
        
    def initialize(self, provider='spotify'):
        """Initialize music provider"""
        try:
            if provider.lower() == 'spotify':
                from connectors.spotify_connector import SpotifyConnector
                self.spotify = SpotifyConnector()
                self.current_provider = 'spotify'
                logger.info("Spotify connector initialized")
                return True
            elif provider.lower() == 'youtube':
                from connectors.yt_music import YTMusic
                self.youtube = YTMusic()
                self.current_provider = 'youtube'
                logger.info("YouTube Music connector initialized")
                return True
        except ImportError as e:
            logger.warning(f"Music module not found: {e}")
            return False
        except Exception as e:
            logger.error(f"Music initialization error: {e}")
            return False
    
    def play(self, track_id=None):
        """Play track"""
        try:
            if self.current_provider == 'spotify' and self.spotify:
                self.spotify.play(track_id)
            elif self.current_provider == 'youtube' and self.youtube:
                self.youtube.play(track_id)
            logger.info(f"Playing track: {track_id}")
            return True
        except Exception as e:
            logger.error(f"Play error: {e}")
            return False
    
    def pause(self):
        """Pause playback"""
        try:
            if self.current_provider == 'spotify' and self.spotify:
                self.spotify.pause()
            elif self.current_provider == 'youtube' and self.youtube:
                self.youtube.pause()
            logger.info("Paused")
            return True
        except Exception as e:
            logger.error(f"Pause error: {e}")
            return False
    
    def next(self):
        """Next track"""
        try:
            if self.current_provider == 'spotify' and self.spotify:
                self.spotify.next()
            elif self.current_provider == 'youtube' and self.youtube:
                self.youtube.next()
            logger.info("Next track")
            return True
        except Exception as e:
            logger.error(f"Next error: {e}")
            return False
    
    def previous(self):
        """Previous track"""
        try:
            if self.current_provider == 'spotify' and self.spotify:
                self.spotify.previous()
            elif self.current_provider == 'youtube' and self.youtube:
                self.youtube.previous()
            logger.info("Previous track")
            return True
        except Exception as e:
            logger.error(f"Previous error: {e}")
            return False
    
    def get_current_track(self):
        """Get current track info"""
        try:
            if self.current_provider == 'spotify' and self.spotify:
                track = self.spotify.get_current_track()
                return {
                    'title': track.get('name', 'Unknown'),
                    'artist': track.get('artist', 'Unknown'),
                    'album': track.get('album', 'Unknown'),
                    'progress': track.get('progress_ms', 0) / 1000,
                    'duration': track.get('duration_ms', 0) / 1000,
                    'is_playing': track.get('is_playing', False),
                }
            elif self.current_provider == 'youtube' and self.youtube:
                track = self.youtube.get_current_track()
                return {
                    'title': track.get('title', 'Unknown'),
                    'artist': track.get('artist', 'Unknown'),
                    'album': track.get('album', 'Unknown'),
                    'progress': track.get('progress', 0),
                    'duration': track.get('duration', 0),
                    'is_playing': track.get('is_playing', False),
                }
        except Exception as e:
            logger.error(f"Get track error: {e}")
        
        return {
            'title': 'No Track',
            'artist': 'Unknown',
            'album': 'Unknown',
            'progress': 0,
            'duration': 0,
            'is_playing': False,
        }
    
    def set_volume(self, volume):
        """Set volume (0-100)"""
        try:
            volume = max(0, min(100, volume))
            if self.current_provider == 'spotify' and self.spotify:
                self.spotify.set_volume(volume)
            elif self.current_provider == 'youtube' and self.youtube:
                self.youtube.set_volume(volume)
            logger.info(f"Volume set to {volume}%")
            return True
        except Exception as e:
            logger.error(f"Volume error: {e}")
            return False
    
    def get_playlist(self):
        """Get current playlist"""
        try:
            if self.current_provider == 'spotify' and self.spotify:
                tracks = self.spotify.get_playlist()
            elif self.current_provider == 'youtube' and self.youtube:
                tracks = self.youtube.get_playlist()
            else:
                tracks = []
            
            return {
                'tracks': [
                    {
                        'id': t.get('id', ''),
                        'title': t.get('name', t.get('title', 'Unknown')),
                        'artist': t.get('artist', 'Unknown'),
                        'album': t.get('album', 'Unknown'),
                    }
                    for t in tracks
                ]
            }
        except Exception as e:
            logger.error(f"Playlist error: {e}")
            return {'tracks': []}


# ============================================
# HOME AUTOMATION INTEGRATION
# ============================================

class HomeAutomationIntegration:
    """Integrate with home automation module"""
    
    def __init__(self):
        self.automation = None
        
    def initialize(self):
        """Initialize home automation"""
        try:
            from connectors.home_automation import HomeAutomation
            self.automation = HomeAutomation()
            logger.info("Home automation initialized")
            return True
        except ImportError as e:
            logger.warning(f"Home automation module not found: {e}")
            return False
        except Exception as e:
            logger.error(f"Home automation initialization error: {e}")
            return False
    
    def control_device(self, device, action):
        """Control a device"""
        try:
            if self.automation:
                if action.lower() == 'on':
                    self.automation.turn_on(device)
                else:
                    self.automation.turn_off(device)
                logger.info(f"Device {device} turned {action}")
                return True
        except Exception as e:
            logger.error(f"Device control error: {e}")
            return False
    
    def get_device_status(self, device):
        """Get device status"""
        try:
            if self.automation:
                status = self.automation.get_status(device)
                return status
        except Exception as e:
            logger.error(f"Device status error: {e}")
        return None


# ============================================
# ANIME FACE INTEGRATION
# ============================================

class AnimeFaceIntegration:
    """Integrate with anime face display"""
    
    def __init__(self):
        self.anime = None
        
    def initialize(self):
        """Initialize anime face"""
        try:
            from anime_face_display import AnimeFaceDisplay
            self.anime = AnimeFaceDisplay()
            logger.info("Anime face display initialized")
            return True
        except ImportError as e:
            logger.warning(f"Anime face module not found: {e}")
            return False
        except Exception as e:
            logger.error(f"Anime face initialization error: {e}")
            return False
    
    def set_emotion(self, emotion):
        """Set anime face emotion"""
        try:
            if self.anime:
                self.anime.set_emotion(emotion)
                logger.info(f"Emotion set to: {emotion}")
                return True
        except Exception as e:
            logger.error(f"Anime emotion error: {e}")
            return False
    
    def start(self):
        """Start anime face display"""
        try:
            if self.anime:
                self.anime.start()
                logger.info("Anime face started")
                return True
        except Exception as e:
            logger.error(f"Anime start error: {e}")
            return False
    
    def stop(self):
        """Stop anime face display"""
        try:
            if self.anime:
                self.anime.stop()
                logger.info("Anime face stopped")
                return True
        except Exception as e:
            logger.error(f"Anime stop error: {e}")
            return False


# ============================================
# INTEGRATION MANAGER
# ============================================

class IntegrationManager:
    """Manage all integrations"""
    
    def __init__(self):
        self.camera = CameraIntegration()
        self.weather = WeatherIntegration()
        self.music = MusicIntegration()
        self.automation = HomeAutomationIntegration()
        self.anime = AnimeFaceIntegration()
        
    def initialize_all(self):
        """Initialize all available integrations"""
        results = {
            'camera': self.camera.initialize(),
            'weather': self.weather.initialize(),
            'music': self.music.initialize(),
            'automation': self.automation.initialize(),
            'anime': self.anime.initialize(),
        }
        
        logger.info(f"Integration results: {results}")
        return results
    
    def status(self):
        """Get integration status"""
        return {
            'camera': self.camera.camera is not None,
            'weather': self.weather.weather is not None,
            'music': self.music.current_provider is not None,
            'automation': self.automation.automation is not None,
            'anime': self.anime.anime is not None,
        }


# Create global integration manager
integrations = IntegrationManager()

if __name__ == '__main__':
    # Test integrations
    logging.basicConfig(level=logging.INFO)
    integrations.initialize_all()
    print("Integration status:", integrations.status())
