"""YouTube Music Player Module

This module provides a comprehensive interface for controlling YouTube Music playback
through mpv player and managing YouTube Music API interactions. It supports playback
of songs, playlists, and artist tracks with volume control.

Attributes:
    IPC_SOCKET: Platform-specific socket path for mpv communication
"""

from pathlib import Path
from dotenv import load_dotenv
from ytmusicapi import YTMusic
from yt_dlp import YoutubeDL
import subprocess
import socket
import os
import time
import sys
import json
import logging
import shutil
import errno

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Add connectors to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'connectors'))



# Use /tmp socket for Linux, Windows named pipe for Windows
IPC_SOCKET = "/tmp/mpvsocket" if os.name == "posix" else r"\\.\pipe\mpvsocket"


class MusicPlayer:
    """
    A comprehensive YouTube Music player controller.
    
    This class manages music playback through mpv, provides YouTube Music search
    capabilities, and controls volume and playback settings.
    
    Attributes:
        player (subprocess.Popen): The mpv process instance
        ytmusic (YTMusic): YouTube Music API client
        volume_controller (VolumeController): System volume control handler
    """

    def __init__(self):
        """Initialize the MusicPlayer with YouTube Music API and volume control."""
        load_dotenv()
        self.player = None
        self.default_volume = 70
        self.mpv_path = self._find_mpv_executable()
        if self.mpv_path:
            logger.info(f"Found mpv executable: {self.mpv_path}")
        else:
            logger.error(
                "mpv executable not found. Install mpv or add it to PATH "
                "(for example: 'apt install mpv' or 'sudo pacman -S mpv'). "
                "Music playback will be disabled."
            )

        self.ytmusic = YTMusic()

        cookie_env = os.getenv("YTDLP_COOKIE_FILE")
        if cookie_env:
            self.ytdlp_cookie_file = os.path.expanduser(cookie_env)
        else:
            self.ytdlp_cookie_file = self._find_cookie_file()

        if self.ytdlp_cookie_file and os.path.exists(self.ytdlp_cookie_file):
            logger.info(f"yt-dlp cookies enabled: {self.ytdlp_cookie_file}")
        else:
            logger.warning(
                "yt-dlp cookie file not found. "
                "Set YTDLP_COOKIE_FILE, place cookies at ~/.config/youtube/cookies.txt, "
                "or add the file path to your service environment."
            )

    def _find_cookie_file(self) -> str:
        """Search common paths for a yt-dlp cookie file."""
        candidates = [
            "~/.config/youtube/cookies.txt",
            "~/.config/yt-dlp/cookies.txt",
            "~/.youtube-cookies.txt",
            "~/youtube-cookies.txt",
            "~/cookies.txt",
        ]
        for candidate in candidates:
            expanded = os.path.expanduser(candidate)
            if os.path.exists(expanded):
                return expanded
        return os.path.expanduser("~/.config/youtube/cookies.txt")

    def _find_mpv_executable(self) -> str:
        """Locate the mpv executable on the host system."""
        candidate = shutil.which("mpv") or shutil.which("mpv.exe")
        if candidate:
            return candidate

        common_paths = [
            "/usr/bin/mpv",
            "/usr/local/bin/mpv",
            os.path.expanduser("~/.local/bin/mpv"),
            os.path.expanduser("~/snap/bin/mpv"),
        ]
        for path in common_paths:
            if path and os.path.exists(path):
                return path

        return None

    def _wait_for_ipc_socket(self, timeout: float = 3.0, interval: float = 0.1) -> bool:
        """Wait for the mpv IPC socket to become available."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                s.settimeout(interval)
                s.connect(IPC_SOCKET)
                s.close()
                return True
            except (FileNotFoundError, ConnectionRefusedError, OSError):
                time.sleep(interval)
        return False

    def _start_mpv(self, cmd: list) -> bool:
        """Start mpv and wait for the IPC socket before returning."""
        if not self.mpv_path:
            logger.error("Cannot start mpv: mpv is not installed or not found in PATH.")
            return False

        self.player = subprocess.Popen(cmd)
        if not self._wait_for_ipc_socket():
            logger.error("mpv IPC socket did not become available after starting mpv.")
            if self.player:
                try:
                    self.player.terminate()
                    self.player.wait(timeout=2)
                except Exception:
                    try:
                        self.player.kill()
                    except Exception:
                        pass
                self.player = None
            return False
        return True

    def search_song(self, query: str) -> tuple:
        """
        Search for a song on YouTube Music.
        
        Args:
            query: The song name or search query
            
        Returns:
            A tuple of (video_id, title, artist) if found, None otherwise
            
        Raises:
            None: Returns None if no song is found
        """
        try:
            results = self.ytmusic.search(query, filter="songs", limit=1)
            if not results:
                logger.warning(f"No song found for query: {query}")
                return None
            video_id = results[0]["videoId"]
            title = results[0]["title"]
            artist = results[0].get("artists", [{}])[0].get("name", "Unknown Artist")
            return video_id, title, artist
        except Exception as e:
            logger.error(f"Error searching song: {e}")
            return None

    def search_artist(self, query: str) -> tuple:
        """
        Search for an artist on YouTube Music.
        
        Args:
            query: The artist name
            
        Returns:
            A tuple of (artist_id, artist_name) if found, None otherwise
        """
        try:
            results = self.ytmusic.search(query, filter="artists", limit=1)
            if not results:
                logger.warning(f"No artist found for query: {query}")
                return None
            artist_id = results[0].get("browseId")
            artist_name = results[0].get("artist", results[0].get("title", "Unknown"))
            if not artist_id:
                logger.warning("Could not extract artist ID from search results")
                return None
            return artist_id, artist_name
        except Exception as e:
            logger.error(f"Error searching artist: {e}")
            return None

    def get_artist_info(self, artist_id: str, limit: int = 10) -> dict:
        """
        Retrieve comprehensive artist information and songs.
        
        This method attempts to gather artist information through multiple strategies:
        1. Initial artist info fetch
        2. Search for all songs by artist name
        3. Album expansion if search results are limited
        
        Args:
            artist_id: The artist's browse ID from YouTube Music
            limit: Maximum number of songs to fetch (None = no limit)
            
        Returns:
            Dictionary containing artist info with 'songs' key containing results,
            or None if operation fails
        """
        try:
            # First get basic artist info
            info = self.ytmusic.get_artist(artist_id)
            logger.info(f"Initial fetch returned info sections: {list(info.keys())}")
            
            all_songs = []
            
            # The get_artist returns limited songs, we need to get more
            # Try to search for all songs by this artist instead
            try:
                logger.info("Searching for all songs by artist...")
                # Search for songs with artist name filter
                artist_name = info.get("name", "")
                search_limit = limit if limit else 100
                search_results = self.ytmusic.search(
                    f"{artist_name}", 
                    filter="songs", 
                    limit=search_limit
                )
                
                if search_results:
                    # Filter to only include songs by this artist
                    for song in search_results:
                        # Stop if we've reached the limit
                        if limit and len(all_songs) >= limit:
                            break
                            
                        song_artists = song.get("artists", [])
                        for artist in song_artists:
                            if artist.get("name", "").lower() == artist_name.lower():
                                if song not in all_songs:  # Avoid duplicates
                                    all_songs.append(song)
                                break
                    
                    logger.info(f"Search returned {len(all_songs)} songs by {artist_name}")
            except Exception as e:
                logger.warning(f"Search method failed: {e}")
            
            # If search didn't work well, use initial songs and expand with albums
            if len(all_songs) <= 5 and (not limit or len(all_songs) < limit):
                logger.info("Search gave limited results, attempting to expand with albums...")
                initial_songs = info.get("songs", {}).get("results", [])
                all_songs = initial_songs.copy()
                
                # Try to get songs from albums
                albums = info.get("albums", {}).get("results", [])
                album_limit = min(10, len(albums))  # Limit to 10 albums to avoid too many requests
                
                for album in albums[:album_limit]:
                    # Stop if we've reached the limit
                    if limit and len(all_songs) >= limit:
                        break
                        
                    try:
                        album_id = album.get("browseId")
                        if album_id:
                            logger.debug(f"Fetching songs from album: {album.get('title', 'Unknown')}")
                            album_info = self.ytmusic.get_album(album_id)
                            album_songs = album_info.get("tracks", [])
                            for track in album_songs:
                                # Stop if we've reached the limit
                                if limit and len(all_songs) >= limit:
                                    break
                                    
                                if track not in all_songs:
                                    all_songs.append(track)
                            time.sleep(0.3)  # Avoid rate limiting
                    except Exception as e:
                        logger.warning(f"Could not fetch album: {e}")
                
                logger.info(f"Expanded to {len(all_songs)} songs using albums")
            
            # Trim to limit if specified
            if limit and len(all_songs) > limit:
                all_songs = all_songs[:limit]
                logger.debug(f"Trimmed to {limit} songs")
            
            # Update info with all songs
            if info:
                info["songs"] = {"results": all_songs}
            
            return info
        except Exception as e:
            logger.error(f"Error getting artist info: {e}", exc_info=True)
            return None

    def search_playlist(self, query: str, limit: int = 5) -> tuple:
        """
        Search for a playlist on YouTube Music.
        
        Args:
            query: Playlist search query (e.g., "romantic songs", "party songs")
            limit: Number of playlists to return in search
            
        Returns:
            A tuple of (playlist_id, playlist_name) if found, None otherwise
        """
        try:
            results = self.ytmusic.search(query, filter="playlists", limit=limit)
            if not results:
                logger.warning(f"No playlist found for: {query}")
                return None
            
            playlist_id = results[0].get("browseId")
            playlist_name = results[0].get("title", "Unknown")
            
            if not playlist_id:
                logger.warning("Could not extract playlist ID from search results")
                return None
            
            return playlist_id, playlist_name
        except Exception as e:
            logger.error(f"Error searching playlist: {e}")
            return None

    def get_playlist_songs(self, playlist_id: str, limit: int = 5) -> list:
        """
        Retrieve songs from a YouTube Music playlist.
        
        Args:
            playlist_id: The playlist's browse ID
            limit: Maximum number of songs to fetch
            
        Returns:
            List of songs in the playlist, empty list if operation fails
        """
        try:
            # Fetch more songs - use 0 for no limit initially, then apply our own limit
            playlist = self.ytmusic.get_playlist(playlist_id, limit=10)
            songs = playlist.get("tracks", [])
            
            # Apply user limit if specified
            if limit and len(songs) > limit:
                songs = songs[:limit]
            
            logger.info(f"Found {len(songs)} songs in playlist")
            return songs
        except Exception as e:
            logger.error(f"Error getting playlist songs: {e}")
            return []

    def _resolve_volume(self, volume: int = None) -> int:
        """Resolve and clamp requested volume to mpv-safe range (0-100)."""
        level = self.default_volume if volume is None else volume
        try:
            level = int(level)
        except (TypeError, ValueError):
            level = self.default_volume
        return max(0, min(100, level))

    def play_playlist(self, playlist_query: str, limit: int = 10, volume: int = None) -> None:
        """
        Search for and play a playlist on YouTube Music.
        
        Retrieves playlist by name and plays all songs using mpv.
        
        Args:
            playlist_query: Playlist name to search for (e.g., "romantic songs")
            limit: Maximum number of songs to play (None = all available)
            volume: Optional mpv volume level (0-100). Uses default volume if None.
        """
        logger.info(f"Searching for playlist: {playlist_query}")
        
        playlist_result = self.search_playlist(playlist_query)
        if not playlist_result:
            logger.error("Failed to find playlist")
            return
        
        playlist_id, playlist_name = playlist_result
        logger.info(f"Found playlist: {playlist_name}")
        
        # Get songs from playlist
        songs = self.get_playlist_songs(playlist_id, limit=limit)
        
        if not songs:
            logger.error(f"No songs found in playlist")
            return
        
        logger.info(f"Found {len(songs)} songs in {playlist_name}")
        
        # Extract video IDs
        video_ids = [song.get("videoId") for song in songs if song.get("videoId")]
        
        if not video_ids:
            logger.error("Could not extract video IDs from playlist")
            return
        
        # Get audio URLs for all tracks (with minimal delay)
        audio_urls = []
        for i, video_id in enumerate(video_ids):
            logger.info(f"Processing track {i+1}/{len(video_ids)}...")
            audio_url = self.get_audio_url(video_id)
            if audio_url:
                audio_urls.append(audio_url)
            time.sleep(0.05)  # Reduced delay - minimal rate limiting
        
        logger.info(f"Processed all {len(audio_urls)} tracks")
        
        if not audio_urls:
            logger.error("Could not get audio URLs")
            return
        
        logger.info(f"Starting playlist '{playlist_name}' with {len(audio_urls)} tracks")
        if not self.mpv_path:
            logger.error("Cannot play playlist: mpv is not installed or not found in PATH.")
            return

        self.stop()
        
        # Start mpv with playlist
        resolved_volume = self._resolve_volume(volume)
        cmd = [
            self.mpv_path,
            "--no-terminal",
            f"--input-ipc-server={IPC_SOCKET}",
            "--playlist-start=0",
            f"--volume={resolved_volume}",
        ] + audio_urls
        if not self._start_mpv(cmd):
            return
        self.set_mpv_volume(resolved_volume)

    def play_by_artist(self, artist_name: str, volume: int = None) -> None:
        """
        Search for an artist and play their top song.
        
        Args:
            artist_name: Name of the artist to search for
            volume: Optional mpv volume level (0-100). Uses default volume if None.
        """
        # Remove "song" from the query if present
        clean_name = artist_name
        
        artist_result = self.search_artist(clean_name)
        if not artist_result:
            logger.error(f"Could not find artist: {artist_name}")
            return
        
        artist_id, artist_name_result = artist_result
        logger.info(f"Found artist: {artist_name_result}")
        
        artist_info = self.get_artist_info(artist_id)
        if not artist_info:
            logger.error("Could not retrieve artist information")
            return
        
        # Check for songs in artist info
        songs = None
        if "topReleases" in artist_info:
            songs = artist_info["topReleases"].get("results", [])
        elif "songs" in artist_info:
            songs = artist_info["songs"].get("results", [])
        
        if songs:
            video_id = songs[0].get("videoId")
            title = songs[0].get("title", "Unknown")
            if video_id:
                logger.info(f"Playing top song by {artist_name_result}: {title}")
                audio_url = self.get_audio_url(video_id)
                if audio_url:
                    if not self.mpv_path:
                        logger.error("Cannot play artist track: mpv is not installed or not found in PATH.")
                        return

                    self.stop()
                    resolved_volume = self._resolve_volume(volume)
                    cmd = [
                        self.mpv_path,
                        "--no-terminal",
                        f"--input-ipc-server={IPC_SOCKET}",
                        f"--volume={resolved_volume}",
                        audio_url
                    ]
                    if not self._start_mpv(cmd):
                        return
                    self.set_mpv_volume(resolved_volume)
                else:
                    logger.error(f"Could not get audio URL for {title}")
            else:
                logger.error(f"Could not get video ID for {title}")
        else:
            logger.error(f"Could not find songs for {artist_name_result}")


    def get_audio_url(self, video_id: str) -> str:
        """
        Extract audio URL from a YouTube video ID using yt-dlp.
        
        Args:
            video_id: The YouTube video ID
            
        Returns:
            The audio URL (best audio format available) or None if extraction fails
        """
        try:
            ydl_opts = {
                "format": "bestaudio/best",
                "quiet": True,
                "no_warnings": True,
                "noplaylist": True,
                "http_headers": {
                    "User-Agent": (
                        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
                    )
                },
            }
            if self.ytdlp_cookie_file and os.path.exists(self.ytdlp_cookie_file):
                ydl_opts["cookiefile"] = self.ytdlp_cookie_file

            with YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(
                    f"https://www.youtube.com/watch?v={video_id}",
                    download=False
                )
                if "url" in info:
                    return info["url"]
                # For merged formats, url is inside requested_formats
                requested = info.get("requested_formats") or info.get("formats", [])
                if requested:
                    return requested[0].get("url")
                logger.warning("Could not find audio URL in response")
                return None
        except Exception as e:
            logger.error(f"Could not extract audio URL: {e}")
            return None

    def play(self, query: str, volume: int = None) -> None:
        """
        Search for a song and play it immediately.
        
        Args:
            query: Song name or search query
            volume: Optional mpv volume level (0-100). Uses default volume if None.
        """
        self.stop()

        result = self.search_song(query)
        if not result:
            logger.error(f"Could not find song: {query}")
            return

        video_id, title, artist = result
        logger.info(f"Playing: {title} by {artist}")

        audio_url = self.get_audio_url(video_id)

        if not audio_url:
            logger.error(f"Could not get audio URL for {title}")
            return

        if not self.mpv_path:
            logger.error("Cannot play song: mpv is not installed or not found in PATH.")
            return

        # Start mpv with IPC enabled
        resolved_volume = self._resolve_volume(volume)
        cmd = [
            self.mpv_path,
            "--no-terminal",
            f"--input-ipc-server={IPC_SOCKET}",
            f"--volume={resolved_volume}",
            audio_url
        ]
        if not self._start_mpv(cmd):
            return
        self.set_mpv_volume(resolved_volume)

    def play_all_artist_tracks(self, artist_name: str, limit: int = 10, volume: int = None) -> None:
        """
        Retrieve and play all available songs from an artist.
        
        Creates a playlist with all songs by the specified artist and
        plays them sequentially using mpv.
        
        Args:
            artist_name: Name of the artist
            limit: Maximum number of songs to play (None = all available)
            volume: Optional mpv volume level (0-100). Uses default volume if None.
        """
        clean_name = artist_name.replace(" song", "").strip()
        
        artist_result = self.search_artist(clean_name)
        if not artist_result:
            logger.error(f"Could not find artist: {artist_name}")
            return
        
        artist_id, artist_name_result = artist_result
        logger.info(f"Found artist: {artist_name_result}")
        
        # Pass limit to get_artist_info
        artist_info = self.get_artist_info(artist_id, limit=limit)
        if not artist_info:
            logger.error("Could not retrieve artist information")
            return
        
        # Get all songs from artist
        songs = None
        if "topReleases" in artist_info:
            songs = artist_info["topReleases"].get("results", [])
        elif "songs" in artist_info:
            songs = artist_info["songs"].get("results", [])
        
        if not songs:
            logger.error(f"No songs found for {artist_name_result}")
            return
        
        logger.info(f"Found {len(songs)} songs by {artist_name_result}")
        
        # Extract video IDs and create playlist
        video_ids = [song.get("videoId") for song in songs if song.get("videoId")]
        
        if not video_ids:
            logger.error("Could not extract video IDs")
            return
        
        # Get audio URLs for all tracks
        audio_urls = []
        for i, video_id in enumerate(video_ids):
            logger.info(f"Processing track {i+1}/{len(video_ids)}...")
            audio_url = self.get_audio_url(video_id)
            if audio_url:
                audio_urls.append(audio_url)
            time.sleep(0.2)  # Small delay to avoid rate limiting
        
        if not audio_urls:
            logger.error("Could not get audio URLs")
            return
        
        logger.info(f"Starting playlist with {len(audio_urls)} tracks")
        self.stop()
        
        volume = self._resolve_volume(volume)
        # Start mpv with all URLs as playlist
        cmd = [
            self.mpv_path,
            "--no-terminal",
            f"--input-ipc-server={IPC_SOCKET}",
            "--playlist-start=0",
            f"--volume={volume}",
        ] + audio_urls
        
        if not self.mpv_path:
            logger.error("Cannot play artist tracks: mpv is not installed or not found in PATH.")
            return

        if not self._start_mpv(cmd):
            return
        self.set_mpv_volume(volume)

    def _send_mpv_command(self, command: str) -> bool:
        """
        Send a JSON command to mpv via IPC socket.
        
        Args:
            command: JSON-formatted command string for mpv
            
        Returns:
            True if command was sent successfully, False otherwise
        """
        if not self.mpv_path:
            logger.error("Cannot send command to mpv: mpv is not installed or not found in PATH.")
            return False

        try:
            s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            s.connect(IPC_SOCKET)
            s.sendall(command.encode() + b'\n')
            s.close()
            return True
        except Exception as e:
            logger.error(f"Error sending command to mpv: {e}")
            return False

    def pause(self) -> None:
        """Pause the current playback."""
        if self._send_mpv_command('{"command": ["set", "pause", "yes"]}'):
            logger.info("Playback paused")
    
    def resume(self) -> None:
        """Resume playback from pause."""
        if self._send_mpv_command('{"command": ["set", "pause", "no"]}'):
            logger.info("Playback resumed")
    
    def toggle_pause(self) -> None:
        """Toggle between play and pause states."""
        if self._send_mpv_command('{"command": ["cycle", "pause"]}'):
            logger.info("Pause toggled")
    
    def next(self) -> None:
        """Skip to the next track in playlist."""
        if self._send_mpv_command('{"command": ["playlist-next"]}'):
            logger.info("Skipped to next track")
    
    def previous(self) -> None:
        """Skip to the previous track in playlist."""
        if self._send_mpv_command('{"command": ["playlist-prev"]}'):
            logger.info("Skipped to previous track")
    
    def set_mpv_volume(self, level: int) -> bool:
        """
        Set mpv player volume directly (0-100).
        
        Args:
            level: Volume level (0-100, where 100 is 100%)
            
        Returns:
            True if volume was set successfully, False otherwise
        """
        if not (0 <= level <= 100):
            logger.warning("Volume must be between 0-100")
            return False
        
        if not self.mpv_path:
            logger.error("Cannot set volume: mpv is not installed or not found in PATH.")
            return False

        # mpv uses 0-100 scale
        cmd = f'{{"command": ["set_property", "volume", {level}]}}'
        if self._send_mpv_command(cmd):
            logger.info(f"Mpv volume set to {level}%")
            return True
        return False

    def mpv_volume_up(self, step: int = 5) -> bool:
        """
        Increase mpv volume by specified step.
        
        Args:
            step: Volume increment (default: 5%)
            
        Returns:
            True if volume was increased successfully, False otherwise
        """
        cmd = f'{{"command": ["add", "volume", {step}]}}'
        if self._send_mpv_command(cmd):
            logger.info(f"Mpv volume increased by {step}%")
            return True
        return False

    def mpv_volume_down(self, step: int = 5) -> bool:
        """
        Decrease mpv volume by specified step.
        
        Args:
            step: Volume decrement (default: 5%)
            
        Returns:
            True if volume was decreased successfully, False otherwise
        """
        cmd = f'{{"command": ["add", "volume", -{step}]}}'
        if self._send_mpv_command(cmd):
            logger.info(f"Mpv volume decreased by {step}%")
            return True
        return False

   

    def stop(self) -> None:
        """
        Stop playback and quit mpv.
        
        Attempts graceful shutdown via IPC first, falls back to process termination.
        """
        try:
            s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            s.connect(IPC_SOCKET)
            s.sendall(b'{"command": ["quit"]}\n')
            s.close()
            logger.info("Playback stopped")
        except OSError as e:
            if e.errno in (errno.ECONNREFUSED, errno.ENOENT, errno.ECONNRESET):
                if os.path.exists(IPC_SOCKET):
                    try:
                        os.remove(IPC_SOCKET)
                        logger.info("Removed stale mpv IPC socket")
                    except OSError:
                        pass
            if self.player:
                try:
                    self.player.terminate()
                    self.player.wait(timeout=2)
                    logger.info("Playback stopped (process terminated)")
                except Exception:
                    try:
                        self.player.kill()
                        logger.info("Playback stopped (process killed)")
                    except Exception:
                        pass
        except Exception as e:
            if self.player:
                try:
                    self.player.terminate()
                    self.player.wait(timeout=2)
                    logger.info("Playback stopped (process terminated)")
                except Exception:
                    try:
                        self.player.kill()
                        logger.info("Playback stopped (process killed)")
                    except Exception:
                        pass

        if self.player:
            self.player = None

# ===============================
# MAIN ENTRY POINT
# ===============================

if __name__ == "__main__":
    """Main execution entry point for the music player."""
    music = MusicPlayer()

    # Example usage:
    # music.play_all_artist_tracks("guru randhawa", limit=10)
    # music.play_playlist("party hindi songs 2026", limit=5)
    music.play("achhi lagti ho hindi song")  # Play a specific song by name
    # time.sleep(3)
    # music.set_mpv_volume(80)
    # music.set_mpv_volume(50)
    # print
    # Playback controls:
    # music.pause()          # Pause playback
    # time.sleep(2)
    # music.resume()         # Resume playback
    # time.sleep(2)
    # music.next()           # Skip to next track
    # music.previous()       # Go to previous track
    # music.set_volume(50)   # Set volume to 50%
    # music.toggle_pause()   # Toggle pause/play
    
    # Keep running to allow control
    # time.sleep(300)
    # music.stop()           # Stop and quit
