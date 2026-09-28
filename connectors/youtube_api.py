from googleapiclient.discovery import build
from dotenv import load_dotenv
import os
import subprocess
import socket
import json
import time
import sys
import threading
import socketserver
import shutil
import importlib.util
from pathlib import Path

load_dotenv()

API_KEY = os.getenv("YOUTUBE_API_KEY")
MPV_SOCKET = "/tmp/mpvsocket"
PLAYER_SOCKET = "/tmp/youtube-player.sock"
_player_server = None
_player_server_lock = threading.Lock()
_player_control_lock = threading.RLock()
current_playlist = []
current_index = 0
mpv_process = None
playback_error = None
playback_loading = False
MPV_LOG = "/tmp/voice_assistant_mpv.log"

youtube = build(
    "youtube",
    "v3",
    developerKey=API_KEY
)

"""
AVAILABLE SEARCH FUNCTIONS:
---------------------------
1. search_youtube(query) - Search any video/song
2. search_genre(genre, max_results=10) - Search songs by genre
3. search_single_song(query) - Search single song in music category
4. search_by_singer(singer_name, max_results=10) - Search songs by artist/singer
5. search_playlist_by_genre(genre, max_results=5) - Search playlists

PLAYBACK FUNCTIONS:
-------------------
1. play_with_mpv(url, title) - Play single song
2. play_all_songs(songs_list) - Play all songs sequentially
3. play_playlist(songs_list, start_index=0) - Play with voice and dashboard controls

USAGE EXAMPLES:
---------------
# Play by singer
songs = search_by_singer("Badshah", max_results=10)
play_playlist(songs)

# Play single song
song = search_single_song("Manali Trance")
play_with_mpv(song["url"], song["title"])

# Play by genre
songs = search_genre("bollywood", max_results=15)
play_playlist(songs)
"""


# -----------------------------------------------------
# Search YouTube
# -----------------------------------------------------

def search_youtube(query):
    request = youtube.search().list(
        part="snippet",
        q=query,
        type="video",
        maxResults=1
    )

    response = request.execute()

    if not response["items"]:
        return None

    item = response["items"][0]

    video_id = item["id"]["videoId"]
    title = item["snippet"]["title"]
    thumbnail = item["snippet"]["thumbnails"]["high"]["url"]

    url = f"https://www.youtube.com/watch?v={video_id}"

    return {
        "title": title,
        "video_id": video_id,
        "url": url,
        "thumbnail": thumbnail
    }

def search_genre(genre, max_results=10):
    request = youtube.search().list(
        part="snippet",
        q=f"{genre} songs",
        type="video",
        videoCategoryId="10",
        maxResults=max_results
    )

    response = request.execute()

    songs = []

    for item in response["items"]:
        video_id = item["id"]["videoId"]

        songs.append({
            "title": item["snippet"]["title"],
            "channel": item["snippet"]["channelTitle"],
            "video_id": video_id,
            "url": f"https://www.youtube.com/watch?v={video_id}",
            "thumbnail": item["snippet"]["thumbnails"]["high"]["url"]
        })

    return songs


def search_single_song(query):
    """Search for a single song in Music category."""
    request = youtube.search().list(
        part="snippet",
        q=query,
        type="video",
        videoCategoryId="10",   # Music category
        maxResults=1
    )

    response = request.execute()

    if not response["items"]:
        return None

    item = response["items"][0]

    video_id = item["id"]["videoId"]

    return {
        "title": item["snippet"]["title"],
        "channel": item["snippet"]["channelTitle"],
        "video_id": video_id,
        "url": f"https://www.youtube.com/watch?v={video_id}",
        "thumbnail": item["snippet"]["thumbnails"]["high"]["url"]
    }


def search_playlist_by_genre(genre, max_results=5):
    """Search for playlists by genre."""
    request = youtube.search().list(
        part="snippet",
        q=f"{genre} playlist",
        type="playlist",
        maxResults=max_results
    )

    response = request.execute()

    playlists = []

    for item in response["items"]:
        playlist_id = item["id"]["playlistId"]

        playlists.append({
            "title": item["snippet"]["title"],
            "channel": item["snippet"]["channelTitle"],
            "playlist_id": playlist_id,
            "description": item["snippet"]["description"],
            "thumbnail": item["snippet"]["thumbnails"]["high"]["url"]
        })

    return playlists


def search_by_singer(singer_name, max_results=10):
    """Search for songs by a specific singer/artist."""
    request = youtube.search().list(
        part="snippet",
        q=f"{singer_name} songs",
        type="video",
        videoCategoryId="10",   # Music category
        maxResults=max_results
    )

    response = request.execute()

    songs = []

    for item in response["items"]:
        video_id = item["id"]["videoId"]

        songs.append({
            "title": item["snippet"]["title"],
            "channel": item["snippet"]["channelTitle"],
            "video_id": video_id,
            "url": f"https://www.youtube.com/watch?v={video_id}",
            "thumbnail": item["snippet"]["thumbnails"]["high"]["url"]
        })

    return songs
# -----------------------------------------------------
# Send command to MPV
# -----------------------------------------------------

def mpv_command(command):
    """Read a complete command response, ignoring unsolicited MPV events."""
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
            client.settimeout(1)
            client.connect(MPV_SOCKET)
            client.sendall((json.dumps({'command': command, 'request_id': 1}) + '\n').encode())
            with client.makefile('rb') as stream:
                while True:
                    line = stream.readline(1024 * 1024)
                    if not line:
                        return None
                    response = json.loads(line)
                    if response.get('request_id') == 1:
                        return response
    except (OSError, ValueError):
        return None


def playback_status():
    """JSON snapshot of the actual player and its in-process playlist."""
    def prop(name, default):
        response = mpv_command(['get_property', name])
        return response.get('data', default) if response and response.get('error') == 'success' else default

    song = current_playlist[current_index] if 0 <= current_index < len(current_playlist) else {}
    active = mpv_process is not None and mpv_process.poll() is None
    return {
        'available': True,
        'error': playback_error,
        'loading': playback_loading,
        'title': song.get('title', 'No Track Playing'),
        'artist': song.get('channel', 'YouTube'),
        'album_art': song.get('thumbnail', ''),
        'is_playing': active and not playback_loading and not prop('pause', True) and not prop('idle-active', True),
        'progress': (prop('time-pos', 0) or 0) if active else 0,
        'duration': (prop('duration', 0) or 0) if active else 0,
        'volume': prop('volume', 70) if active else 70,
        'current_index': current_index,
        'tracks': [{'title': item['title'], 'artist': item.get('channel', 'YouTube')}
                   for item in current_playlist],
    }


def control_playback(payload):
    """Keep dashboard controls in the process that owns the playlist."""
    action = payload.get('action')
    with _player_control_lock:
        if action == 'play' and 'track_index' in payload:
            play_index(payload['track_index'])
        elif action == 'play' and (mpv_process is None or mpv_process.poll() is not None):
            play_index(current_index)
        elif action in ('play', 'pause', 'stop', 'volume', 'seek'):
            if action in ('play', 'pause'):
                command = ['set_property', 'pause', action == 'pause']
            elif action == 'stop':
                command = ['stop']
            else:
                value = float(payload.get('value', 0))
                if not 0 <= value <= 100:
                    raise ValueError('Volume and seek must be between 0 and 100.')
                command = (['set_property', 'volume', value] if action == 'volume'
                           else ['seek', value, 'absolute-percent'])
            response = mpv_command(command)
            if not response or response.get('error') != 'success':
                raise ValueError('The music player could not apply the command.')
        elif action == 'next':
            play_next()
        elif action == 'previous':
            play_previous()
        else:
            raise ValueError('Unsupported music command.')


def start_player_server():
    """Expose the existing player to the local dashboard; no second player."""
    global _player_server
    with _player_server_lock:
        if _player_server is not None:
            return
        if os.path.exists(PLAYER_SOCKET):
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as probe:
                probe.settimeout(1)
                try:
                    probe.connect(PLAYER_SOCKET)
                except (ConnectionRefusedError, FileNotFoundError):
                    os.unlink(PLAYER_SOCKET)
                else:
                    raise RuntimeError('Another YouTube player is already serving the dashboard.')

        class Handler(socketserver.StreamRequestHandler):
            def handle(self):
                self.request.settimeout(5)
                try:
                    line = self.rfile.readline(8192)
                    if not line:
                        return
                    payload = json.loads(line)
                    if not isinstance(payload, dict):
                        raise ValueError('Invalid music request.')
                    if payload.get('action') != 'status':
                        control_playback(payload)
                    response = {'status': playback_status()}
                except Exception as exc:
                    response = {'error': str(exc)}
                try:
                    self.wfile.write((json.dumps(response) + '\n').encode())
                except OSError:
                    pass

        class Server(socketserver.ThreadingUnixStreamServer):
            daemon_threads = True

        _player_server = Server(PLAYER_SOCKET, Handler)
        os.chmod(PLAYER_SOCKET, 0o600)
        threading.Thread(target=_player_server.serve_forever, daemon=True).start()


# -----------------------------------------------------
# Volume
# -----------------------------------------------------

def set_volume(value):
    volume = int(float(value))

    mpv_command([
        "set_property",
        "volume",
        volume
    ])


# -----------------------------------------------------
# Pause / Resume
# -----------------------------------------------------

def toggle_pause():
    # MPV owns pause state, including changes made through the dashboard.
    return mpv_command(['cycle', 'pause'])


# -----------------------------------------------------
# Stop
# -----------------------------------------------------

def stop_music():

    mpv_command(["stop"])


def play_index(index):
    global current_index
    with _player_control_lock:
        if type(index) is not int or not 0 <= index < len(current_playlist):
            raise ValueError('Track is not in the current playlist.')
        current_index = index
        song = current_playlist[index]
        process = play_with_mpv(song['url'], song['title'])
        if process is None:
            raise RuntimeError('Could not start music playback.')
        return process


def play_next():
    if current_index < len(current_playlist) - 1:
        return play_index(current_index + 1)


def play_previous():
    if current_index > 0:
        return play_index(current_index - 1)


# -----------------------------------------------------
# Play with MPV

def play_with_mpv(url, title, song_info=None):
    global current_playlist, current_index
    with _player_control_lock:
        # Direct single-song playback must replace any previous playlist.
        if song_info is not None or not current_playlist or current_playlist[current_index]['url'] != url:
            current_playlist = [song_info or {'url': url, 'title': title}]
            current_index = 0
        start_player_server()
        return _start_mpv(url, title)


def youtube_extract_command(url):
    # Use the assistant's installed version, not the older system executable.
    command = [sys.executable, '-m', 'yt_dlp', '--no-playlist', '--no-cache-dir',
               '--socket-timeout', '10', '-f', 'bestaudio/best', '-g']
    node = shutil.which('node')
    if not node:
        playwright = importlib.util.find_spec('playwright')
        if playwright and playwright.origin:
            bundled = Path(playwright.origin).parent / 'driver' / 'node'
            if bundled.is_file():
                node = str(bundled)
    if node:
        command.extend(['--js-runtimes', f'node:{node}'])
    return command + [url]


def _start_mpv(url, title):
    global mpv_process, playback_error, playback_loading
    playback_error = None
    playback_loading = True
    try:
        if mpv_process and mpv_process.poll() is None:
            mpv_process.terminate()
            try:
                mpv_process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                mpv_process.kill()
                mpv_process.wait(timeout=2)
        mpv_process = None
        if os.path.exists(MPV_SOCKET):
            os.remove(MPV_SOCKET)

        result = subprocess.run(youtube_extract_command(url), capture_output=True,
                                text=True, timeout=45)
        streams = result.stdout.strip().splitlines()
        if result.returncode != 0 or not streams:
            print('YouTube extraction failed:', result.stderr[-2000:])
            raise RuntimeError('YouTube could not provide an audio stream. Please try another song.')

        mpv_cmd = ['mpv', '--no-video', '--no-sub', '--no-terminal',
                   f'--title={title}', '--volume=70',
                   f'--input-ipc-server={MPV_SOCKET}', streams[0]]
        # Avoid unread PIPE buffers; preserve startup/audio errors for diagnosis.
        with open(MPV_LOG, 'w') as log:
            mpv_process = subprocess.Popen(mpv_cmd, stdout=log, stderr=subprocess.STDOUT)

        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            if mpv_process.poll() is not None:
                raise RuntimeError(f'Music player exited before audio started. See {MPV_LOG}.')
            audio = mpv_command(['get_property', 'audio-out-params'])
            position = mpv_command(['get_property', 'time-pos'])
            if (audio and audio.get('error') == 'success' and audio.get('data') and
                    position and position.get('error') == 'success' and
                    isinstance(position.get('data'), (int, float)) and position['data'] > 0):
                print(f'Audio playback confirmed: {title}')
                return mpv_process
            time.sleep(0.2)
        raise RuntimeError('Audio did not start within 15 seconds. Please retry.')
    except Exception as exc:
        playback_error = str(exc) if not isinstance(exc, subprocess.TimeoutExpired) else 'YouTube took too long to load the song. Please retry.'
        if mpv_process is not None and mpv_process.poll() is None:
            mpv_process.terminate()
            try:
                mpv_process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                mpv_process.kill()
                mpv_process.wait(timeout=2)
        raise RuntimeError(playback_error) from exc
    finally:
        playback_loading = False


def play_all_songs(songs_list):
    """Play all songs from a list sequentially."""
    for idx, song in enumerate(songs_list):
        print(f"\n[{idx+1}/{len(songs_list)}] {song['title']}")
        mpv_process = play_with_mpv(song["url"], song["title"])
        
        if mpv_process:
            # Wait for song to finish playing
            mpv_process.wait()
        else:
            print(f"Skipping: {song['title']}")


def play_playlist(songs_list, start_index=0):
    """Start a playlist controlled by voice and the centralized dashboard."""
    global current_playlist, current_index
    if type(start_index) is not int or not 0 <= start_index < len(songs_list):
        raise ValueError('Choose a valid starting track.')
    with _player_control_lock:
        current_playlist = songs_list
        current_index = start_index
        return play_index(start_index)
