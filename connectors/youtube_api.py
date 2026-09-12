from googleapiclient.discovery import build
from dotenv import load_dotenv
import os
import subprocess
import socket
import json
import time
import sys
import threading

# Try to import tkinter - may not be available on headless systems
try:
    import tkinter as tk
    from tkinter import ttk
    HAS_DISPLAY = os.environ.get('DISPLAY') is not None
except (ImportError, RuntimeError):
    tk = None
    ttk = None
    HAS_DISPLAY = False

load_dotenv()

API_KEY = os.getenv("YOUTUBE_API_KEY")
MPV_SOCKET = "/tmp/mpvsocket"
current_playlist = []
current_index = 0
mpv_process = None
music_ui_root = None  # Global reference to music UI window
music_ui_labels = {}  # Dictionary to store UI labels for updates

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
3. play_playlist(songs_list, start_index=0) - Play with UI controls

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
    try:
        client = socket.socket(
            socket.AF_UNIX,
            socket.SOCK_STREAM
        )

        client.connect(MPV_SOCKET)

        message = json.dumps({
            "command": command
        }) + "\n"

        client.send(message.encode())

        response = client.recv(4096)

        client.close()

        return json.loads(response.decode())

    except Exception as e:
        print("MPV IPC error:", e)
        return None


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

paused = False


def toggle_pause():
    global paused

    paused = not paused

    mpv_command([
        "set_property",
        "pause",
        paused
    ])


# -----------------------------------------------------
# Stop
# -----------------------------------------------------

def stop_music():

    mpv_command(["stop"])


# Play next song
def play_next():
    global current_index, mpv_process
    
    if current_index < len(current_playlist) - 1:
        current_index += 1
        
        # Stop current playback
        if mpv_process and mpv_process.poll() is None:
            mpv_process.terminate()
        
        # Play next song (don't call play_playlist, just play_with_mpv)
        song = current_playlist[current_index]
        mpv_process = play_with_mpv(song["url"], song["title"])
        
        # Update UI immediately
        update_song_info()
    else:
        print("Already at last song")


# Play previous song
def play_previous():
    global current_index, mpv_process
    
    if current_index > 0:
        current_index -= 1
        
        # Stop current playback
        if mpv_process and mpv_process.poll() is None:
            mpv_process.terminate()
        
        # Play previous song (don't call play_playlist, just play_with_mpv)
        song = current_playlist[current_index]
        mpv_process = play_with_mpv(song["url"], song["title"])
        
        # Update UI immediately
        update_song_info()
    else:
        print("Already at first song")


# Update song info in UI
def update_song_info():
    """Update UI labels with current song info."""
    global music_ui_labels, current_playlist, current_index
    
    if not music_ui_labels:  # No UI active
        return
        
    if current_playlist and current_index < len(current_playlist):
        song = current_playlist[current_index]
        
        # Update title
        if "title" in music_ui_labels:
            music_ui_labels["title"].config(text=song["title"])
        
        # Update channel/artist
        if "channel" in music_ui_labels:
            music_ui_labels["channel"].config(text=song['channel'])
        
        # Update index display
        if "index" in music_ui_labels:
            index_text = f"Song {current_index + 1} of {len(current_playlist)}"
            music_ui_labels["index"].config(text=index_text)
        
        # Keep UI on top
        global music_ui_root
        if music_ui_root:
            try:
                music_ui_root.lift()
                music_ui_root.focus_force()
            except:
                pass


# -----------------------------------------------------
# Play with MPV

def play_with_mpv(url, title):
    global mpv_process

    try:
        # Remove old socket
        if os.path.exists(MPV_SOCKET):
            os.remove(MPV_SOCKET)

        print(f"\nPlaying: {title}")

        # Kill previous process if running
        if mpv_process and mpv_process.poll() is None:
            mpv_process.terminate()
            time.sleep(0.5)

        # Extract streaming URL using yt-dlp
        try:
            result = subprocess.run(
                ["yt-dlp", "-f", "bestaudio", "-g", url],
                capture_output=True,
                text=True,
                timeout=15
            )
            
            if result.returncode == 0:
                stream_url = result.stdout.strip().split('\n')[0]
                print(f"Got stream URL from yt-dlp")
            else:
                # Fallback to direct URL if yt-dlp fails
                print(f"yt-dlp failed: {result.stderr[:100]}")
                stream_url = url
        except subprocess.TimeoutExpired:
            print("yt-dlp timeout, using direct URL")
            stream_url = url
        except FileNotFoundError:
            print("yt-dlp not found, using direct URL")
            stream_url = url

        print(f"Stream URL: {stream_url[:100]}")

        mpv_cmd = [
            "mpv",
            "--no-video",
            "--no-sub",
            f"--title={title}",
            "--volume=70",
            f"--input-ipc-server={MPV_SOCKET}",
            stream_url
        ]

        print(f"Starting MPV with: {' '.join(mpv_cmd[:5])}...")

        mpv_process = subprocess.Popen(
            mpv_cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        
        print(f"MPV process started: PID={mpv_process.pid}")

        return mpv_process

    except FileNotFoundError:
        print("MPV not installed")
        print("sudo apt install mpv")
        return None
    except Exception as e:
        print(f"Error in play_with_mpv: {e}")
        return None


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
    """Play songs with UI controls."""
    global current_playlist, current_index
    
    current_playlist = songs_list
    current_index = start_index
    
    # Launch UI only once when starting playlist
    if HAS_DISPLAY and tk is not None:
        launch_music_ui(songs_list)
    
    if current_index < len(current_playlist):
        song = current_playlist[current_index]
        return play_with_mpv(song["url"], song["title"])


# =====================================================
# Launch Music UI
# =====================================================

def launch_music_ui(songs_list):
    """Launch Tkinter music player UI in a separate thread - only once per playlist."""
    
    global music_ui_root
    
    if not tk or not HAS_DISPLAY:
        return
    
    # Close existing window if running
    if music_ui_root is not None:
        try:
            music_ui_root.destroy()
        except:
            pass
    
    try:
        # Create UI in a separate thread to not block music playback
        ui_thread = threading.Thread(target=lambda: create_music_ui(songs_list), daemon=True)
        ui_thread.start()
    except Exception as e:
        print(f"Error launching UI: {e}")


def create_music_ui(songs_list):
    """Create and run the Tkinter music player UI."""
    
    global music_ui_root, music_ui_labels
    
    if not tk:
        return
    
    try:
        music_ui_root = tk.Tk()
        music_ui_root.title("🎵 Music Player")
        music_ui_root.geometry("500x400")
        music_ui_root.resizable(False, False)  # Prevent resizing
        
        # Position in top-right corner to avoid fullscreen app overlap
        music_ui_root.geometry("+1400+20")
        
        # Always on top - use skipTaskbar and always-on-top
        music_ui_root.attributes('-topmost', True)
        music_ui_root.attributes('-type', 'splash')  # Make it act like a floating window
        music_ui_root.focus_force()  # Force focus on window creation
        
        # Title
        title_label = tk.Label(
            music_ui_root,
            text=songs_list[0]["title"] if songs_list else "Playing...",
            font=("Arial", 14, "bold"),
            wraplength=450,
            fg="black"
        )
        title_label.pack(pady=15)
        music_ui_labels["title"] = title_label
        
        # Artist/Channel
        channel_label = tk.Label(
            music_ui_root,
            text=songs_list[0]["channel"] if songs_list else "YouTube Music",
            font=("Arial", 11),
            fg="gray"
        )
        channel_label.pack(pady=5)
        music_ui_labels["channel"] = channel_label
        
        # Status
        status_label = tk.Label(
            music_ui_root,
            text="▶ Now Playing",
            font=("Arial", 10, "bold"),
            fg="green"
        )
        status_label.pack(pady=10)
        music_ui_labels["status"] = status_label
        
        # Volume display
        volume_label = tk.Label(
            music_ui_root,
            text="Volume: 70%",
            font=("Arial", 9),
            fg="blue"
        )
        volume_label.pack(pady=5)
        music_ui_labels["volume"] = volume_label
        
        # Index display
        index_label = tk.Label(
            music_ui_root,
            text=f"Song 1 of {len(songs_list)}",
            font=("Arial", 9),
            fg="purple"
        )
        index_label.pack(pady=3)
        music_ui_labels["index"] = index_label
        
        # Button frame 1 - Playback controls
        button_frame1 = tk.Frame(music_ui_root)
        button_frame1.pack(pady=10)
        
        # Previous button
        def on_prev():
            try:
                play_previous()
                music_ui_root.lift()  # Bring window to front
                music_ui_root.focus_force()  # Force focus
            except Exception as e:
                print(f"Error in previous: {e}")
        
        prev_btn = tk.Button(
            button_frame1,
            text="⏮ Previous",
            command=on_prev,
            bg="#ff6600",
            fg="white",
            font=("Arial", 10, "bold"),
            width=10,
            padx=5,
            pady=8
        )
        prev_btn.pack(side="left", padx=5)
        
        # Pause/Resume button
        pause_state = {"paused": False}
        
        def on_pause():
            try:
                toggle_pause()
                if pause_state["paused"]:
                    pause_state["paused"] = False
                    pause_btn.config(text="⏸ Pause")
                    music_ui_labels["status"].config(text="▶ Playing")
                else:
                    pause_state["paused"] = True
                    pause_btn.config(text="▶ Resume")
                    music_ui_labels["status"].config(text="⏸ Paused")
                music_ui_root.lift()
                music_ui_root.focus_force()
            except Exception as e:
                print(f"Error in pause: {e}")
        
        pause_btn = tk.Button(
            button_frame1,
            text="⏸ Pause",
            command=on_pause,
            bg="#0099ff",
            fg="white",
            font=("Arial", 10, "bold"),
            width=10,
            padx=5,
            pady=8
        )
        pause_btn.pack(side="left", padx=5)
        music_ui_labels["pause_btn"] = pause_btn
        
        # Next button
        def on_next():
            try:
                play_next()
                music_ui_root.lift()  # Bring window to front
                music_ui_root.focus_force()  # Force focus
            except Exception as e:
                print(f"Error in next: {e}")
        
        next_btn = tk.Button(
            button_frame1,
            text="Next ⏭",
            command=on_next,
            bg="#00dd66",
            fg="white",
            font=("Arial", 10, "bold"),
            width=10,
            padx=5,
            pady=8
        )
        next_btn.pack(side="left", padx=5)
        
        # Button frame 2 - Volume and Stop controls
        button_frame2 = tk.Frame(music_ui_root)
        button_frame2.pack(pady=10)
        
        # Volume decrease
        def decrease_volume():
            try:
                current_vol = int(music_ui_labels["volume"].cget("text").split(": ")[1].rstrip("%"))
                new_vol = max(0, current_vol - 10)
                set_volume(new_vol)
                music_ui_labels["volume"].config(text=f"Volume: {new_vol}%")
                music_ui_root.lift()
                music_ui_root.focus_force()
            except Exception as e:
                print(f"Error decreasing volume: {e}")
        
        vol_down = tk.Button(
            button_frame2,
            text="🔉 -",
            command=decrease_volume,
            bg="#ff9900",
            fg="white",
            font=("Arial", 10, "bold"),
            width=8,
            padx=5,
            pady=8
        )
        vol_down.pack(side="left", padx=5)
        
        # Volume increase
        def increase_volume():
            try:
                current_vol = int(music_ui_labels["volume"].cget("text").split(": ")[1].rstrip("%"))
                new_vol = min(100, current_vol + 10)
                set_volume(new_vol)
                music_ui_labels["volume"].config(text=f"Volume: {new_vol}%")
                music_ui_root.lift()
                music_ui_root.focus_force()
            except Exception as e:
                print(f"Error increasing volume: {e}")
        
        vol_up = tk.Button(
            button_frame2,
            text="🔊 +",
            command=increase_volume,
            bg="#ff9900",
            fg="white",
            font=("Arial", 10, "bold"),
            width=8,
            padx=5,
            pady=8
        )
        vol_up.pack(side="left", padx=5)
        
        # Stop button
        def on_stop():
            try:
                global music_ui_root
                stop_music()
                music_ui_labels["status"].config(text="⏹ Stopped")
                # Close UI after stopping
                if music_ui_root:
                    music_ui_root.destroy()
                    music_ui_root = None
            except Exception as e:
                print(f"Error stopping: {e}")
        
        stop_btn = tk.Button(
            button_frame2,
            text="⏹ Stop",
            command=on_stop,
            bg="#dd0000",
            fg="white",
            font=("Arial", 10, "bold"),
            width=8,
            padx=5,
            pady=8
        )
        stop_btn.pack(side="left", padx=5)
        
        # Keep window on top - refresh every 100ms and maintain focus
        def keep_on_top():
            try:
                if music_ui_root:
                    music_ui_root.attributes('-topmost', True)
                    music_ui_root.lift()  # Bring to front
                    music_ui_root.after(500, keep_on_top)  # Check every 500ms
            except:
                pass
        
        # Bind focus loss to restore focus immediately
        def on_focus_out(event):
            try:
                if music_ui_root:
                    music_ui_root.lift()
                    music_ui_root.focus_force()
            except:
                pass
        
        music_ui_root.bind("<FocusOut>", on_focus_out)
        
        keep_on_top()
        
        music_ui_root.mainloop()
        
    except Exception as e:
        print(f"Error creating UI: {e}")