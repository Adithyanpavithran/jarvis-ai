import os
import sys
import json
from pathlib import Path
from app.utils.logger import get_app_dir, log

# Default Settings Schema
DEFAULT_SETTINGS = {
    "wake_word": "hey jarvis",
    "wake_mode": "voice",            # "voice", "double_clap", "typed"
    "force_typed_input": False,
    "stt_backend": "google",          # "whisper", "google"
    "whisper_model": "tiny.en",
    "silence_limit": 0.8,
    "tts_backend": "edge-tts",        # "edge-tts", "piper", "sapi"
    "tts_voice": "en-US-JennyNeural",
    "tts_rate": "+0%",
    "tts_volume": "+0%",
    "ollama_enabled": True,
    "ollama_api_url": "http://localhost:11434",
    "ollama_model": "mistral",
    "ollama_temperature": 0.7,
    "theme": "dark",                 # "dark", "light"
    "auto_start": False,
    "focus_cursor_on_double_clap": True,
    "open_new_cursor_on_double_clap": False,
    "open_claude_in_chrome": False,
    "spotify_uri": "https://open.spotify.com/track/39shmbIHICJ2Wxnk1fPSdz?si=2900c75c2e2d4b82",
    "claude_chrome_monitor": 1,
    "open_chrome_fullscreen": True,
    "chrome_separate_site_profiles": False,
    "claude_code_url": "https://claude.ai/new",
    "jarvis_after_song_delay_s": 1.0
}

class SettingsManager:
    def __init__(self):
        self.app_dir = get_app_dir()
        self.settings_file = self.app_dir / "settings.json"
        self.settings = DEFAULT_SETTINGS.copy()
        self.load()

    def load(self):
        """Load settings from JSON file. Create defaults if missing."""
        if self.settings_file.exists():
            try:
                with open(self.settings_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    # Merge defaults for any missing keys
                    for k, v in DEFAULT_SETTINGS.items():
                        self.settings[k] = data.get(k, v)
                log.info("Settings loaded successfully.")
            except Exception as e:
                log.error("Failed to load settings file: %s. Using defaults.", e)
        else:
            self.save()

    def save(self):
        """Save settings to JSON file."""
        try:
            with open(self.settings_file, "w", encoding="utf-8") as f:
                json.dump(self.settings, f, indent=4)
            log.info("Settings saved successfully.")
        except Exception as e:
            log.error("Failed to save settings: %s", e)

    def get(self, key, default=None):
        return self.settings.get(key, default)

    def set(self, key, value):
        self.settings[key] = value
        self.save()

        # Handle system changes immediately
        if key == "auto_start":
            self.set_auto_start_registry(value)

    def set_auto_start_registry(self, enable: bool):
        """Enable or disable auto-start with Windows via Registry."""
        if sys.platform != "win32":
            return
        
        try:
            import winreg
            key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
            app_name = "JarvisAssistant"
            
            # Determine command: if running from script, use python executable + script path
            if getattr(sys, 'frozen', False):
                # Compiled executable
                cmd = f'"{sys.executable}"'
            else:
                # Script run
                main_script = Path(__file__).resolve().parents[2] / "app" / "main.py"
                cmd = f'"{sys.executable}" "{main_script}"'

            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_SET_VALUE)
            if enable:
                winreg.SetValueEx(key, app_name, 0, winreg.REG_SZ, cmd)
                log.info("Windows registry auto-start enabled: %s", cmd)
            else:
                try:
                    winreg.DeleteValue(key, app_name)
                    log.info("Windows registry auto-start disabled.")
                except FileNotFoundError:
                    pass
            winreg.CloseKey(key)
        except Exception as e:
            log.error("Failed to set Windows registry auto-start: %s", e)

settings_manager = SettingsManager()
