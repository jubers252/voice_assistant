"""YouTube Music Player Module

This module provides a comprehensive interface for controlling YouTube Music playback
through mpv player and managing YouTube Music API interactions. It supports playback
of songs, playlists, and artist tracks with volume control.

Attributes:
    IPC_SOCKET: Platform-specific socket path for mpv communication
"""

from ytmusicapi import YTMusic
from yt_dlp import YoutubeDL
import subprocess
import socket
import os
import time
import sys
import json
import logging

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
        self.player = None
        self.ytmusic = YTMusic()
        self.set_mpv_volume(80)

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

    def search_playlist(self, query: str, limit: int = 10) -> tuple:
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

    def get_playlist_songs(self, playlist_id: str, limit: int = 10) -> list:
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
            playlist = self.ytmusic.get_playlist(playlist_id, limit=50)
            songs = playlist.get("tracks", [])
            
            # Apply user limit if specified
            if limit and len(songs) > limit:
                songs = songs[:limit]
            
            logger.info(f"Found {len(songs)} songs in playlist")
            return songs
        except Exception as e:
            logger.error(f"Error getting playlist songs: {e}")
            return []

    def play_playlist(self, playlist_query: str, limit: int = 10) -> None:
        """
        Search for and play a playlist on YouTube Music.
        
        Retrieves playlist by name and plays all songs using mpv.
        
        Args:
            playlist_query: Playlist name to search for (e.g., "romantic songs")
            limit: Maximum number of songs to play (None = all available)
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
        self.stop()
        
        # Start mpv with playlist
        cmd = [
            "mpv",
            "--no-terminal",
            f"--input-ipc-server={IPC_SOCKET}",
            "--playlist-start=0"
        ] + audio_urls
        
        self.player = subprocess.Popen(cmd)
        time.sleep(0.5)

    def play_by_artist(self, artist_name: str) -> None:
        """
        Search for an artist and play their top song.
        
        Args:
            artist_name: Name of the artist to search for
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
                    self.stop()
                    self.player = subprocess.Popen([
                        "mpv",
                        "--no-terminal",
                        f"--input-ipc-server={IPC_SOCKET}",
                        audio_url
                    ])
                    time.sleep(0.5)
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
                "format": "bestaudio",
                "quiet": True,
                "no_warnings": True,
            }
            with YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(
                    f"https://www.youtube.com/watch?v={video_id}",
                    download=False
                )
                if "url" in info:
                    return info["url"]
                else:
                    logger.warning("Could not find audio URL in response")
                    return None
        except Exception as e:
            logger.error(f"Could not extract audio URL: {e}")
            return None

    def play(self, query: str) -> None:
        """
        Search for a song and play it immediately.
        
        Args:
            query: Song name or search query
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

        # Start mpv with IPC enabled
        self.player = subprocess.Popen([
            "mpv",
            "--no-terminal",
            f"--input-ipc-server={IPC_SOCKET}",
            audio_url
        ])

        time.sleep(0.5)  # give mpv time to start

    def play_all_artist_tracks(self, artist_name: str, limit: int = 10) -> None:
        """
        Retrieve and play all available songs from an artist.
        
        Creates a playlist with all songs by the specified artist and
        plays them sequentially using mpv.
        
        Args:
            artist_name: Name of the artist
            limit: Maximum number of songs to play (None = all available)
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
        
        # Start mpv with all URLs as playlist
        cmd = [
            "mpv",
            "--no-terminal",
            f"--input-ipc-server={IPC_SOCKET}",
            "--playlist-start=0"
        ] + audio_urls
        
        self.player = subprocess.Popen(cmd)
        time.sleep(0.5)

    def _send_mpv_command(self, command: str) -> bool:
        """
        Send a JSON command to mpv via IPC socket.
        
        Args:
            command: JSON-formatted command string for mpv
            
        Returns:
            True if command was sent successfully, False otherwise
        """
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
        except Exception as e:
            # Fallback: send SIGTERM to process
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
    # music.play_playlist("romantic hindi songs", limit=5)
    # music.play("shaky song")  # Play a specific song by name
    # time.sleep(3)
    
    # music.set_volume(80)
    # print
    # Playback controls:
    music.pause()          # Pause playback
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
