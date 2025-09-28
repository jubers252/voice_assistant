import json
from spotipy import Spotify
import os
import pandas as pd
import subprocess
import spotipy as sp
from spotipy.oauth2 import SpotifyOAuth
import time

class InvalidSearchError(Exception):
    pass


class SpotifyConnector:

    def __init__(self, spotify: Spotify):
        self.spotify = spotify
        self.device_id = None
    

    def _find_device(self):
        """Find and cache the first active device. Returns dict with id/name or False."""
        try:
            devices = self.spotify.devices()
            print(devices)
            if len(devices['devices']) > 0:
                self.device_id = devices['devices'][0]['id']
                return {"device_id": devices['devices'][0]['id'], "device_name": devices['devices'][0]['name']}
            self.device_id = None
            return False
        except Exception:
            return False
    
        
    
    def get_album_uri(self, name: str) -> str:
        original = name
        name = name.replace(' ', '+')
        results = self.spotify.search(q=name, limit=1, type='album')
        if not results['albums']['items']:
            raise InvalidSearchError(f'No album named "{original}"')
        album_uri = results['albums']['items'][0]['uri']
        return album_uri

    def get_artist_uri(self, name: str) -> str:
        original = name
        name = name.replace(' ', '+')
        results = self.spotify.search(q=name, limit=1, type='artist')
        if not results['artists']['items']:
            raise InvalidSearchError(f'No artist named "{original}"')
        artist_uri = results['artists']['items'][0]['uri']
        print(results['artists']['items'][0]['name'])
        return artist_uri

    def search_tracks_by_keyword(self, keyword: str, limit=5):
        """
        Search for tracks using keywords and return multiple results
        
        Args:
            keyword: Search query (can be song name, artist, or both)
            limit: Maximum number of results to return
            
        Returns:
            List of track dictionaries with name, artist, and uri
        """
        try:
            # Clean and format the search query
            search_query = keyword.replace(' ', '+')
            
            # Search for tracks
            results = self.spotify.search(q=search_query, limit=limit, type='track')
            
            tracks = []
            for track in results['tracks']['items']:
                track_info = {
                    'name': track['name'],
                    'artist': ', '.join([artist['name'] for artist in track['artists']]),
                    'album': track['album']['name'],
                    'uri': track['uri'],
                    'popularity': track['popularity'],
                    'duration_ms': track['duration_ms']
                }
                tracks.append(track_info)
            
            return tracks
            
        except Exception as e:
            print(f"Search error: {e}")
            return []

    def smart_play_by_keyword(self, keyword: str, device_id=None):
        """
        Intelligently search and play music by keyword with fallback options
        
        Args:
            keyword: Search query (song name, artist, or both)
            device_id: Spotify device ID
            
        Returns:
            Dictionary with success status and message
        """
        try:
            if device_id is None:
                device_id = self.device_id
            if device_id is None:
                raise Exception("No active Spotify device found.")
            
            # Try to activate device first
            try:
                self.spotify.transfer_playback(device_id=device_id, force_play=False)
            except Exception:
                pass
            
            # Search for tracks
            tracks = self.search_tracks_by_keyword(keyword, limit=10)
            
            if not tracks:
                return {
                    'success': False,
                    'message': f"Sorry, I couldn't find any songs matching '{keyword}' on Spotify.",
                    'suggestion': "Try using different keywords or check the spelling."
                }
            
            # Play the most popular/relevant track (first result is usually best match)
            best_track = tracks[0]
            
            try:
                self.set_volume(100, device_id=device_id)
                self.spotify.start_playback(device_id=device_id, uris=[best_track['uri']])
                
                return {
                    'success': True,
                    'message': f"Playing '{best_track['name']}' by {best_track['artist']}",
                    'track_info': best_track,
                    'alternatives': tracks[1:3] if len(tracks) > 1 else []  # Show 2 alternatives
                }
                
            except Exception as play_error:
                return {
                    'success': False,
                    'message': f"Found the song but couldn't play it: {play_error}",
                    'track_info': best_track
                }
                
        except Exception as e:
            return {
                'success': False,
                'message': f"Search failed: {e}",
                'suggestion': "Try checking your internet connection or Spotify login."
            }

    def get_track_uri(self, name: str) -> str:
        """Enhanced track search with better error handling"""
        original = name
        
        # Try exact search first
        tracks = self.search_tracks_by_keyword(name, limit=1)
        
        if not tracks:
            raise InvalidSearchError(f'No track found matching "{original}". Try using different keywords.')
        
        return tracks[0]['uri']

    def play_album(self, device_id=None, uri=None):
        if device_id is None:
            raise Exception("No active Spotify device found. Please open Spotify and start playing something.")
        self.set_volume(100, device_id=device_id)
        self.spotify.start_playback(device_id=device_id, context_uri=uri)

    def play_artist(self, device_id=None, uri=None):
        if device_id is None:
            raise Exception("No active Spotify device found. Please open Spotify and start playing something.")
        self.set_volume(100, device_id=device_id)
        self.spotify.start_playback(device_id=device_id, context_uri=uri)

    def play_track(self, device_id=None, uri=None):
        if device_id is None:
            raise Exception("No active Spotify device found. Please open Spotify and start playing something.")
        self.set_volume(100, device_id=device_id)
        self.spotify.start_playback(device_id=device_id, uris=[uri])
    
    def stop_playback(self, device_id=None):
        """Stop/pause current playback"""
        if device_id is None:
            device_id = self.device_id
        if device_id is None:
            raise Exception("No active Spotify device found. Please open Spotify and start playing something.")
        self.spotify.pause_playback(device_id=device_id)
    
    def resume_playback(self, device_id=None):
        """Resume playback of the currently paused song."""
        if device_id is None:
            device_id = self.device_id
        if device_id is None:
            raise Exception("No active Spotify device found. Please open Spotify and start playing something.")
        self.set_volume(100, device_id=device_id)
        self.spotify.start_playback(device_id=device_id)

    def play_next(self, device_id=None):
        """Skip to next song"""
        if device_id is None:
            device_id = self.device_id
        if device_id is None:
            raise Exception("No active Spotify device found. Please open Spotify and start playing something.")
        self.spotify.next_track(device_id=device_id)

    def open_spotify_in_edge(self):
        """Open Spotify Web Player in browser (Linux compatible)"""
        try:
            spotify_url = "https://open.spotify.com"
            
            # Try different browsers on Linux/Raspberry Pi
            browsers = [
                "chromium-browser",  # Raspberry Pi default
                "firefox",
                "google-chrome",
                "chromium",
                "xdg-open"  # Default opener
            ]
            
            for browser in browsers:
                try:
                    subprocess.run([browser, spotify_url], check=True)
                    print(f"Opened Spotify in {browser}")
                    return
                except (subprocess.CalledProcessError, FileNotFoundError):
                    continue
            
            # If no browser worked, try generic open
            try:
                import webbrowser
                webbrowser.open(spotify_url)
                print("Opened Spotify in default web browser")
            except:
                print("Could not open Spotify web player")
                
        except Exception as e:
            print(f"Error opening Spotify: {e}")

    def handle_action(self, tool_info, device_id=None):
        """Handle structured tool_info input and perform the requested Spotify action with enhanced search."""
        # Use cached device_id if not provided
        if device_id is None:
            device_id = self.device_id
            
        try:
            if tool_info.get("action") == "play":
                target = tool_info.get("target")
                name = tool_info.get("name")
                
                # If we have a device but it might be inactive, try to transfer playback first
                if device_id:
                    try:
                        self.spotify.transfer_playback(device_id=device_id, force_play=False)
                        print("Activated web player")
                    except Exception as e:
                        print(f"Note: Could not activate web player: {e}")
                
                # Use smart search for tracks (most common use case)
                if target == "track" or target is None:
                    result = self.smart_play_by_keyword(name, device_id=device_id)
                    
                    if result['success']:
                        message = result['message']
                        # Add alternatives if available
                        if result.get('alternatives'):
                            alt_names = [f"'{alt['name']}' by {alt['artist']}" for alt in result['alternatives']]
                            message += f". Other options: {', '.join(alt_names[:2])}"
                        return message
                    else:
                        # Try fallback to album/artist search if track search fails
                        try:
                            print(f"Track search failed, trying album search for: {name}")
                            uri = self.get_album_uri(name)
                            self.play_album(device_id=device_id, uri=uri)
                            return f"Couldn't find the exact song, but playing album: {name}"
                        except:
                            try:
                                print(f"Album search failed, trying artist search for: {name}")
                                uri = self.get_artist_uri(name)
                                self.play_artist(device_id=device_id, uri=uri)
                                return f"Couldn't find the song or album, but playing music by artist: {name}"
                            except:
                                return result['message'] + " " + result.get('suggestion', '')
                                
                elif target == "album":
                    try:
                        uri = self.get_album_uri(name)
                        self.play_album(device_id=device_id, uri=uri)
                        return f"Playing album: {name}"
                    except InvalidSearchError:
                        return f"Sorry, couldn't find album '{name}' on Spotify. Try a different search term."
                        
                elif target == "artist":
                    try:
                        uri = self.get_artist_uri(name)
                        self.play_artist(device_id=device_id, uri=uri)
                        return f"Playing music by artist: {name}"
                    except InvalidSearchError:
                        return f"Sorry, couldn't find artist '{name}' on Spotify. Try a different search term."
                else:
                    # Generic search - try smart keyword search
                    result = self.smart_play_by_keyword(name, device_id=device_id)
                    return result['message'] + " " + result.get('suggestion', '') if not result['success'] else result['message']
                    
            elif tool_info.get("action") == "stop":
                self.stop_playback(device_id=device_id)
                return "Playback stopped"
            elif tool_info.get("action") == "resume":
                self.resume_playback(device_id=device_id)
                return "Playback resumed"
            elif tool_info.get("action") == "next":
                self.play_next(device_id=device_id)
                return "Playing next song"
            else:
                return "Unsupported Spotify action."
        except Exception as e:
            return f"Spotify error: {e}"
        
    def set_volume(self, volume_percent, device_id=None):
        """Set the volume for the active device (0-100)."""
        if device_id is None:
            device_id = self.device_id
        if device_id is None:
            raise Exception("No active Spotify device found. Please open Spotify and start playing something.")
        if not (0 <= volume_percent <= 100):
            raise ValueError("Volume percent must be between 0 and 100.")
        self.spotify.volume(volume_percent, device_id=device_id)

    def main(self, tools_data):
        """Test spotify_connector using JSON input"""
        try:
            # Look for setup.txt in the parent directory (main project folder)
            setup_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'setup.txt')
            if not os.path.exists(setup_path):
                return f"Setup file not found at: {setup_path}"
            setup = pd.read_csv(setup_path, sep='=', index_col=0, header=None).squeeze()
            scope = "user-read-private user-read-playback-state user-modify-playback-state user-read-currently-playing"
            auth_manager = SpotifyOAuth(
                client_id=setup['client_id'],
                client_secret=setup['client_secret'],
                redirect_uri=setup['redirect_uri'],
                scope=scope,
                username=setup['username']
            )
            spotify = sp.Spotify(auth_manager=auth_manager)
            connector = SpotifyConnector(spotify)
            device_info = connector._find_device()
            if not device_info:
                print("No active device found, opening Spotify in Edge...")
                connector.open_spotify_in_edge()
                time.sleep(10)
                device_info = connector._find_device()
            if not device_info:
                return "No active device found after opening Spotify."
            print(f"Using active device: {device_info['device_name']} ({device_info['device_id']})")
            result = connector.handle_action(tools_data, device_id=device_info['device_id'])
            return result
        except Exception as e:
            return f"Error: {e}"
        
if __name__ == "__main__":
    # Create a temporary connector just to open Spotify in Edge
    tool_data = {"action": "stop", "name": "saiyyara", "target": "artist"}
    obj = SpotifyConnector(None)
    # obj.open_spotify_in_edge()
    obj.main(tool_data)
    pass