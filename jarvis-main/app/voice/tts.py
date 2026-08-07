import os
import sys
import asyncio
import hashlib
import tempfile
import subprocess
from pathlib import Path
from app.utils.logger import get_app_dir, log
from app.config.settings import settings_manager

class TextToSpeechManager:
    def __init__(self):
        self.app_dir = get_app_dir()
        self.cache_dir = self.app_dir / ".cache" / "tts"
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._init_pygame()
        self.sapi_voice = None
        import threading
        self.speech_lock = threading.Lock()
        self.is_speaking = False

    def _init_pygame(self):
        """Initialize pygame mixer for audio playback."""
        try:
            import pygame
            if not pygame.mixer.get_init():
                pygame.mixer.init()
        except Exception as e:
            log.error("Failed to initialize pygame mixer: %s", e)

    def _get_cache_path(self, text: str, voice: str, rate: str, volume: str) -> Path:
        """Generate a unique cache file path using MD5 hash of voice config and text."""
        key = f"{text}_{voice}_{rate}_{volume}".encode("utf-8")
        h = hashlib.md5(key).hexdigest()
        return self.cache_dir / f"{h}.mp3"

    def _play_audio_file(self, path: Path) -> bool:
        """Play a saved MP3/WAV file using pygame."""
        try:
            import pygame
            if not pygame.mixer.get_init():
                pygame.mixer.init()
            pygame.mixer.music.load(str(path))
            pygame.mixer.music.play()
            while pygame.mixer.music.get_busy():
                pygame.time.wait(100)
            pygame.mixer.music.unload()
            return True
        except Exception as e:
            log.error("Failed to play audio file %s: %s", path, e)
            return False

    def speak(self, text: str):
        """Speak the text. Uses threads or runs asyncio internally."""
        if not text.strip():
            return

        if self.is_speaking:
            self.stop()

        with self.speech_lock:
            self.is_speaking = True
            try:
                self._do_speak(text)
            finally:
                self.is_speaking = False

    def _do_speak(self, text: str):

        backend = settings_manager.get("tts_backend", "edge-tts")
        voice = settings_manager.get("tts_voice", "en-US-JennyNeural")
        rate = settings_manager.get("tts_rate", "+0%")
        volume = settings_manager.get("tts_volume", "+0%")

        # Try to use cached file first
        cache_path = self._get_cache_path(text, voice, rate, volume)
        if cache_path.is_file():
            if self._play_audio_file(cache_path):
                return

        # 1. Edge-TTS (Default, high quality Microsoft Azure voices)
        if backend == "edge-tts":
            try:
                import edge_tts
                tmp_path = cache_path.with_suffix(".tmp.mp3")
                communicate = edge_tts.Communicate(text, voice=voice, rate=rate, volume=volume)
                
                # Run async save in sync context
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                loop.run_until_complete(communicate.save(str(tmp_path)))
                loop.close()
                
                if tmp_path.is_file():
                    tmp_path.replace(cache_path)
                    self._play_audio_file(cache_path)
                    return
            except Exception as e:
                log.error("edge-tts generation failed: %s. Falling back.", e)

        # 2. Piper TTS (Local high quality speech)
        if backend == "piper":
            try:
                piper_path = settings_manager.get("piper_executable_path", "piper")
                model_path = settings_manager.get("piper_model_path", "en_US-lessac-medium.onnx")
                
                if os.path.exists(piper_path) or subprocess.run(["where", "piper"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0:
                    wav_path = cache_path.with_suffix(".wav")
                    # Run piper CLI process
                    # piper expects text on stdin, outputs WAV to file
                    cmd = [piper_path, "-m", model_path, "-f", str(wav_path)]
                    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    proc.communicate(input=text.encode("utf-8"))
                    proc.wait()
                    
                    if wav_path.is_file():
                        # Save wav as cached path
                        wav_path.replace(cache_path) # pygame can play WAV directly too
                        self._play_audio_file(cache_path)
                        return
            except Exception as e:
                log.error("Piper TTS failed: %s", e)

        # 3. Fallback: SAPI (Windows Native Offline TTS - Female Voice)
        if sys.platform == "win32":
            try:
                import win32com.client
                if self.sapi_voice is None:
                    self.sapi_voice = win32com.client.Dispatch("SAPI.SpVoice")
                    # Explicitly select female voice (Microsoft Zira / Female)
                    for v in self.sapi_voice.GetVoices():
                        desc = v.GetDescription().lower()
                        if "zira" in desc or "female" in desc or "eva" in desc or "hazel" in desc:
                            self.sapi_voice.Voice = v
                            break
                self.sapi_voice.Speak(text)
                return
            except Exception as e:
                log.error("SAPI voice failed: %s", e)

        # 4. Final Fallback: PowerShell SpeechSynthesizer (Female Voice)
        if sys.platform == "win32":
            try:
                with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False, suffix=".txt") as tmp:
                    tmp.write(text)
                    tmp_path = tmp.name
                safe_path = tmp_path.replace("'", "''")
                ps_cmd = (
                    "Add-Type -AssemblyName System.Speech; "
                    "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
                    "try { $s.SelectVoiceByHints([System.Speech.Synthesis.VoiceGender]::Female) } catch {}; "
                    f"$s.Speak((Get-Content -Raw -Path '{safe_path}'))"
                )
                subprocess.run(
                    ["powershell", "-NoProfile", "-Command", ps_cmd],
                    check=True,
                    creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
                )
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass
                return
            except Exception as e:
                log.error("PowerShell TTS failed: %s", e)

        log.warning("No TTS backend was able to play speech: %s", text)

    def stop(self):
        """Stop any ongoing speech playback."""
        log.info("Interruption requested: stopping speech.")
        try:
            import pygame
            if pygame.mixer.get_init():
                pygame.mixer.music.stop()
                pygame.mixer.music.unload()
        except Exception as e:
            log.error("Failed to stop pygame music: %s", e)
            
        if sys.platform == "win32" and self.sapi_voice is not None:
            try:
                self.sapi_voice.Speak("", 1) # SVSFPurgeBeforeSpeak = 1
            except Exception as e:
                log.debug("Failed to stop SAPI voice: %s", e)

tts_manager = TextToSpeechManager()
