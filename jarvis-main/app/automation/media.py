import sys
import subprocess
from app.utils.logger import log
from app.ai.tool_calls import tool_registry

@tool_registry.register("play_media")
def play_media(action: str) -> str:
    """Control media playback (play, pause, next, prev) via PowerShell."""
    if sys.platform != "win32":
        return "Media control is only supported on Windows."
    
    # Map actions to Virtual Key Codes sent via PowerShell com shell
    # 179 = Play/Pause, 176 = Next Track, 177 = Previous Track
    action_map = {
        "play": 179,
        "pause": 179,
        "next": 176,
        "prev": 177,
        "previous": 177
    }

    keycode = action_map.get(action.lower())
    if not keycode:
        return f"Unknown media action '{action}'. Use play, pause, next, or prev."

    ps_cmd = f"$w = New-Object -ComObject Wscript.Shell; $w.SendKeys([char]{keycode})"
    try:
        subprocess.run(["powershell", "-NoProfile", "-Command", ps_cmd], creationflags=subprocess.CREATE_NO_WINDOW)
        log.info("Media action executed: %s", action)
        return f"Media command '{action}' sent successfully."
    except Exception as e:
        log.error("Failed to execute media command %s: %s", action, e)
        return f"Failed to execute media command."

@tool_registry.register("clipboard_get")
def clipboard_get() -> str:
    """Retrieve text from the clipboard."""
    if sys.platform != "win32":
        return "Clipboard is only supported on Windows."
    
    try:
        res = subprocess.run(
            ["powershell", "-NoProfile", "-Command", "Get-Clipboard"],
            capture_output=True,
            text=True,
            creationflags=subprocess.CREATE_NO_WINDOW
        )
        val = res.stdout.strip()
        log.info("Read clipboard contents.")
        return val if val else "Clipboard is empty."
    except Exception as e:
        log.error("Failed to get clipboard: %s", e)
        return "Failed to read clipboard."

@tool_registry.register("clipboard_set")
def clipboard_set(text: str) -> str:
    """Copy text to the clipboard."""
    if sys.platform != "win32":
        return "Clipboard is only supported on Windows."
    
    try:
        # Pass text to clipboard using PowerShell pipeline
        cmd = f'Set-Clipboard -Value "{text.replace(chr(34), chr(96) + chr(34))}"'
        subprocess.run(
            ["powershell", "-NoProfile", "-Command", cmd],
            creationflags=subprocess.CREATE_NO_WINDOW
        )
        log.info("Set clipboard contents.")
        return "Copied text to clipboard."
    except Exception as e:
        log.error("Failed to set clipboard: %s", e)
        return "Failed to copy text to clipboard."

@tool_registry.register("open_spotify")
def open_spotify(query: str = None) -> str:
    """Open Spotify desktop app or search for a query/song on Spotify."""
    import urllib.parse
    log.info("Opening Spotify...")
    if query:
        search_url = "https://open.spotify.com/search/" + urllib.parse.quote(query)
        try:
            webbrowser.open(search_url)
            return f"Opened Spotify search for '{query}'."
        except Exception as e:
            log.warning("Could not open Spotify search: %s", e)
    try:
        if sys.platform == "win32":
            os.startfile("spotify:")
            return "Opened Spotify application."
    except Exception:
        pass
    webbrowser.open("https://open.spotify.com")
    return "Opened Spotify Web Player."

def _get_first_youtube_video_id(query: str) -> str | None:
    """Helper to query YouTube search page and extract the first video ID."""
    import urllib.request
    import urllib.parse
    import re
    search_url = "https://www.youtube.com/results?search_query=" + urllib.parse.quote(query)
    try:
        req = urllib.request.Request(
            search_url,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
            }
        )
        with urllib.request.urlopen(req, timeout=5) as response:
            html = response.read().decode('utf-8')
            video_ids = re.findall(r"/watch\?v=([a-zA-Z0-9_-]{11})", html)
            if video_ids:
                # Remove duplicates while keeping order
                unique_ids = []
                for vid in video_ids:
                    if vid not in unique_ids:
                        unique_ids.append(vid)
                return unique_ids[0]
    except Exception as e:
        log.warning("Failed to fetch first YouTube video ID: %s", e)
    return None

@tool_registry.register("open_youtube")
def open_youtube(query: str = None) -> str:
    """Open YouTube or search for a video query on YouTube."""
    import urllib.parse
    import webbrowser
    log.info("Opening YouTube...")
    if query:
        cleaned = query.strip()
        if cleaned.lower().startswith("play "):
            cleaned = cleaned[5:].strip()
        if cleaned.lower().startswith("music "):
            cleaned = cleaned[6:].strip()
            
        # Try to get direct video link for auto-play
        video_id = _get_first_youtube_video_id(cleaned)
        if video_id:
            url = f"https://www.youtube.com/watch?v={video_id}"
            msg = f"Playing '{cleaned}' directly on YouTube."
        else:
            url = "https://www.youtube.com/results?search_query=" + urllib.parse.quote(cleaned)
            msg = f"Opened YouTube search for '{query}'."
    else:
        url = "https://www.youtube.com"
        msg = "Opened YouTube."
        
    try:
        webbrowser.open(url)
        return msg
    except Exception as e:
        log.warning("Could not open YouTube: %s", e)
        return f"Failed to open YouTube: {e}"

@tool_registry.register("play_song")
def play_song(uri: str = None) -> str:
    """Open/Play a specific song URI (Spotify/YouTube link). Uses default URI from settings if none specified."""
    from app.config.settings import settings_manager
    u = uri or settings_manager.get("spotify_uri", "")
    u = u.strip()
    if not u:
        return "No song URI specified or configured in settings."
    try:
        if sys.platform == "win32":
            os.startfile(u)
        else:
            webbrowser.open(u)
        return f"Playing song URI: {u}."
    except Exception as e:
        log.warning("Could not play song URI: %s", e)
        return f"Failed to play song. Error: {e}"

@tool_registry.register("open_youtube_music")
def open_youtube_music(query: str = None) -> str:
    """Open YouTube Music or search for a track on YouTube Music."""
    import urllib.parse
    import webbrowser
    log.info("Opening YouTube Music...")
    if query:
        cleaned = query.strip()
        if cleaned.lower().startswith("play "):
            cleaned = cleaned[5:].strip()
            
        # Try to get direct video link for auto-play on YT Music
        video_id = _get_first_youtube_video_id(cleaned)
        if video_id:
            url = f"https://music.youtube.com/watch?v={video_id}"
            msg = f"Playing '{cleaned}' directly on YouTube Music."
        else:
            url = "https://music.youtube.com/search?q=" + urllib.parse.quote(cleaned)
            msg = f"Opened YouTube Music search for '{query}'."
    else:
        url = "https://music.youtube.com"
        msg = "Opened YouTube Music."
        
    try:
        webbrowser.open(url)
        return msg
    except Exception as e:
        log.warning("Could not open YouTube Music: %s", e)
        return f"Failed to open YouTube Music: {e}"

import os
import webbrowser


