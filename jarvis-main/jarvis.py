#!/usr/bin/env python3
"""
Desktop clap listener: reads the default microphone and logs when two loud transients
(a double clap) are detected within a short time window.

Run:
  python -m pip install -r requirements.txt
  python clap_listen.py

Tuning (constants below):
  SAMPLE_RATE   — usually 44100 or 48000; match your device if needed.
  BLOCK_MS      — analysis window size; smaller = snappier, noisier.
  SPIKE_RATIO   — how many times louder than the noise floor counts as a clap;
                    raise if false triggers; lower if claps are missed.
  COOLDOWN_S    — minimum seconds between double-clap logs (debounce).
  MIN_DOUBLE_GAP_S / MAX_DOUBLE_GAP_S — allowed time between the two claps.
  RETRIGGER_RATIO — audio must fall below threshold * this before another hit counts.
  NOISE_FLOOR_ALPHA — closer to 1 = slower baseline adaptation to room noise.
  MIN_RMS       — ignore spikes below this absolute level (float audio ~ [-1, 1]).
  SONG_URI      — Spotify or YouTube URL/URI to open on each double clap (empty = log only).
  OPEN_CLAUDE_CODE_IN_CHROME — Claude in Chrome after Spotify (CLAUDE_CODE_URL).
  CHROME_SEPARATE_SITE_PROFILES — Windows: if True, uses temp --user-data-dir per site (not your normal profile).
    Default False so Claude uses your usual Chrome profile and logins; enable only if the window keeps opening on the same monitor and you accept a separate profile for automation.
  OPEN_CHROME_FULLSCREEN — Fullscreen on the chosen monitor (Windows: new window is detected and snapped with SetWindowPos).
  JARVIS_WELCOME_* — TTS after the song (Edge TTS). Configure via environment or a `.env`
    file next to this script (EDGE_TTS_VOICE, etc.).
    With JARVIS_WELCOME_CACHE_ENABLED, audio is saved under `.cache/jarvis_welcome/` (WAV) and
    replayed when phrase + voice + rate + volume match—no repeat API call. Delete that folder
    or set JARVIS_WELCOME_CACHE_ENABLED=False to force a fresh fetch.
  The welcome sequence runs only once per process. The assistant speaks in the background so Cursor
    opens without waiting for playback to finish (restart the script to run again).
"""

from __future__ import annotations

import asyncio
import hashlib
import io
import logging
import os
import shutil
import json
import subprocess
import sys
import tempfile
import threading
import time
import urllib.parse
import urllib.request
import wave
import webbrowser
from pathlib import Path

try:
    import win32com.client as win32com_client
except Exception:  # pragma: no cover
    win32com_client = None

from dotenv import load_dotenv
import numpy as np
import sounddevice as sd
import speech_recognition as sr

try:
    import whisper
except Exception:  # pragma: no cover
    whisper = None

# --- tuning knobs -----------------------------------------------------------
SAMPLE_RATE = 44100
BLOCK_MS = 40
CHANNELS = 1

SPIKE_RATIO = 7.0
COOLDOWN_S = 0.45
MIN_DOUBLE_GAP_S = 0.05
MAX_DOUBLE_GAP_S = 0.35
RETRIGGER_RATIO = 0.55
NOISE_FLOOR_ALPHA = 0.992
MIN_RMS = 0.012
QUIET_GATE_MULT = 2.2  # update noise floor only when below floor * this
# Startup mic probe: if default input RMS stays below this, scan for a louder device.
INPUT_PROBE_S = 0.5
INPUT_SILENT_RMS = 0.001

# Spotify: "spotify:track:TRACK_ID" or https://open.spotify.com/track/...
# YouTube: https://www.youtube.com/watch?v=...
SONG_URI = "https://open.spotify.com/track/39shmbIHICJ2Wxnk1fPSdz?si=2900c75c2e2d4b82"

# Cursor is disabled for this wake-up flow.
FOCUS_EXISTING_CURSOR_ON_DOUBLE_CLAP = False
OPEN_NEW_CURSOR_ON_DOUBLE_CLAP = False
CURSOR_OPEN_FULLSCREEN = False

# Google Chrome (fallback: default browser). URLs overridable in .env.
OPEN_CLAUDE_CODE_IN_CHROME = True
OPEN_CHROME_FULLSCREEN = True
# False = default Chrome profile (your normal user, extensions, cookies). True = temp dirs under %TEMP% per site.
CHROME_SEPARATE_SITE_PROFILES = False
# Which physical screen (1 = leftmost/top-first after sorting). Windows only; ignored elsewhere.
CLAUDE_CHROME_MONITOR = 1

load_dotenv(Path(__file__).resolve().parent / ".env")

JARVIS_WELCOME_ENABLED = True
JARVIS_INPUT_DEVICE = "Microphone Array"
JARVIS_WELCOME_PHRASE = (
    "Jarvis online. "
    "I am ready to help you. "
    "What would you like me to do?"
)
JARVIS_WEBSITE_DIR = (os.environ.get("JARVIS_WEBSITE_DIR") or "").strip()
JARVIS_WEBSITE_BUILD_CMD = (os.environ.get("JARVIS_WEBSITE_BUILD_CMD") or "").strip()
JARVIS_WEBSITE_URL = (os.environ.get("JARVIS_WEBSITE_URL") or "http://localhost:8000").strip()
OLLAMA_ENABLED = (os.environ.get("OLLAMA_ENABLED") or "True").strip().lower() in ("true", "1", "yes")
OLLAMA_API_URL = (os.environ.get("OLLAMA_API_URL") or "http://localhost:11434").strip()
OLLAMA_MODEL = (os.environ.get("OLLAMA_MODEL") or "mistral").strip()
OLLAMA_TEMPERATURE = float((os.environ.get("OLLAMA_TEMPERATURE") or "0.7").strip() or 0.7)
# Seconds after launching SONG_URI before speaking (gives Spotify/browser time to start).
JARVIS_AFTER_SONG_DELAY_S = 1.0
# Save Edge TTS WAV under .cache/jarvis_welcome/; replay skips the API when the text/voice/rate/volume match.
JARVIS_WELCOME_CACHE_ENABLED = True
JARVIS_WAKE_MODE = (os.environ.get("JARVIS_WAKE_MODE") or "double_clap").strip().lower()
JARVIS_STT_BACKEND = (os.environ.get("JARVIS_STT_BACKEND") or "whisper").strip().lower()
JARVIS_WHISPER_MODEL = (os.environ.get("JARVIS_WHISPER_MODEL") or "tiny.en").strip()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("clap_listen")
_WHISPER_MODEL_CACHE: dict[str, object] = {}


def block_samples() -> int:
    n = int(SAMPLE_RATE * BLOCK_MS / 1000)
    return max(n, 1)


def rms_mono(block: np.ndarray) -> float:
    if block.ndim > 1:
        block = np.mean(block.astype(np.float64), axis=1)
    else:
        block = block.astype(np.float64)
    if block.size == 0:
        return 0.0
    return float(np.sqrt(np.mean(block**2)))


def _input_devices() -> list[tuple[int, dict]]:
    return [
        (i, dev)
        for i, dev in enumerate(sd.query_devices())
        if dev["max_input_channels"] >= 1
    ]


def _resolve_input_device_index(spec: str) -> int:
    spec = spec.strip()
    if spec.isdigit():
        idx = int(spec)
        sd.query_devices(idx)
        return idx
    needle = spec.lower()
    for idx, dev in _input_devices():
        if needle in dev["name"].lower():
            return idx
    raise ValueError(f"No input device matches {spec!r}")


def _probe_input_max_rms(device: int, blocksize: int) -> float | None:
    try:
        with sd.InputStream(
            device=device,
            samplerate=SAMPLE_RATE,
            channels=CHANNELS,
            dtype="float32",
            blocksize=blocksize,
        ) as stream:
            peak = 0.0
            deadline = time.monotonic() + INPUT_PROBE_S
            while time.monotonic() < deadline:
                data, _ = stream.read(blocksize)
                peak = max(peak, rms_mono(data))
            return peak
    except sd.PortAudioError:
        return None


def _choose_input_device(blocksize: int) -> int:
    log.info("Audio devices:\n%s", sd.query_devices())

    override = (os.environ.get("JARVIS_INPUT_DEVICE") or JARVIS_INPUT_DEVICE or "").strip()
    if override:
        try:
            idx = _resolve_input_device_index(override)
        except ValueError as e:
            log.error("%s", e)
            log.error("Set JARVIS_INPUT_DEVICE to a device index or name substring.")
            raise SystemExit(1) from e
        name = sd.query_devices(idx)["name"]
        peak = _probe_input_max_rms(idx, blocksize)
        log.info("Using JARVIS_INPUT_DEVICE [%d]: %s", idx, name)
        if peak is None:
            log.warning("Could not open configured mic; trying anyway.")
            return idx
        if peak < INPUT_SILENT_RMS:
            log.warning(
                "Configured mic looks silent (probe rms=%.5f). "
                "Checking other inputs for a louder device.",
                peak,
            )
            for candidate_idx, dev in _input_devices():
                if candidate_idx == idx:
                    continue
                candidate_peak = _probe_input_max_rms(candidate_idx, blocksize)
                if candidate_peak is not None and candidate_peak >= INPUT_SILENT_RMS:
                    log.info(
                        "Falling back to alternate microphone [%d]: %s (probe rms=%.5f)",
                        candidate_idx,
                        dev["name"],
                        candidate_peak,
                    )
                    return candidate_idx
            log.warning("No other active mic found; using configured input anyway.")
            return idx
        log.info("Mic probe OK (rms=%.5f).", peak)
        return idx

    default = sd.default.device[0]
    if default is not None and default >= 0:
        default_name = sd.query_devices(default)["name"]
        peak = _probe_input_max_rms(default, blocksize)
        if peak is not None and peak >= INPUT_SILENT_RMS:
            log.info(
                "Using default microphone [%d]: %s (probe rms=%.5f)",
                default,
                default_name,
                peak,
            )
            return default
        log.warning(
            "Default mic [%d] %s is silent or unavailable (probe rms=%s); "
            "scanning other inputs...",
            default,
            default_name,
            f"{peak:.5f}" if peak is not None else "unopenable",
        )

    best_idx: int | None = None
    best_peak = -1.0
    for idx, dev in _input_devices():
        if default is not None and idx == default:
            continue
        peak = _probe_input_max_rms(idx, blocksize)
        if peak is not None and peak > best_peak:
            best_peak = peak
            best_idx = idx

    if best_idx is not None and best_peak >= INPUT_SILENT_RMS:
        log.info(
            "Auto-selected microphone [%d]: %s (probe rms=%.5f)",
            best_idx,
            sd.query_devices(best_idx)["name"],
            best_peak,
        )
        return best_idx

    if default is not None and default >= 0:
        log.warning("No active mic found; falling back to default [%d].", default)
        return default
    inputs = _input_devices()
    if not inputs:
        log.error("No input devices found.")
        raise SystemExit(1)
    idx, dev = inputs[0]
    log.warning("No active mic found; falling back to [%d] %s.", idx, dev["name"])
    return idx


def _normalize_edge_tts_percent(value: str, default: str) -> str:
    value = (value or default).strip()
    if not value:
        return default
    if value == "0%":
        return "+0%"
    if value[0] not in "+-":
        if value.endswith("%") and value[1:].isdigit():
            return "+" + value
    return value


def edge_tts_env_config() -> tuple[str, str, str]:
    """voice, rate, volume."""
    voice = (os.environ.get("EDGE_TTS_VOICE") or "").strip()
    rate = _normalize_edge_tts_percent(os.environ.get("EDGE_TTS_RATE", ""), "+0%")
    volume = _normalize_edge_tts_percent(os.environ.get("EDGE_TTS_VOLUME", ""), "+0%")
    return voice, rate, volume


def _jarvis_welcome_cache_dir() -> Path:
    base = Path(__file__).resolve().parent
    override = (os.environ.get("JARVIS_WELCOME_CACHE_DIR") or "").strip()
    if override:
        return Path(override).expanduser().resolve()
    return base / ".cache" / "jarvis_welcome"


def _jarvis_welcome_cache_path(
    text: str, voice: str, rate: str, volume: str
) -> Path:
    key = f"{text}|{voice}|{rate}|{volume}".encode()
    digest = hashlib.sha256(key).hexdigest()[:24]
    return _jarvis_welcome_cache_dir() / f"{digest}.wav"


def _play_pcm_wav_file(path: Path) -> bool:
    try:
        with wave.open(str(path), "rb") as wf:
            ch = wf.getnchannels()
            sw = wf.getsampwidth()
            rate = wf.getframerate()
            raw = wf.readframes(wf.getnframes())
    except (OSError, wave.Error) as e:
        log.warning("Could not read cached welcome audio: %s", e)
        return False
    if not raw:
        return False
    if sw != 2:
        log.warning("Unsupported cached WAV sample width=%s; only 16-bit PCM is supported.", sw)
        return False
    pcm_i16 = np.frombuffer(raw, dtype=np.int16)
    if ch == 2:
        pcm_i16 = pcm_i16.reshape(-1, 2)
        pcm_f = pcm_i16.astype(np.float32) / 32768.0
    else:
        pcm_f = pcm_i16.astype(np.float32) / 32768.0
    try:
        sd.play(pcm_f, rate)
        sd.wait()
    except Exception as e:
        log.warning("Could not play cached welcome audio: %s", e)
        return False
    return True


def _save_pcm_wav_file(path: Path, pcm_bytes: bytes, sample_rate: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    try:
        with wave.open(str(tmp), "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(sample_rate)
            wf.writeframes(pcm_bytes)
        tmp.replace(path)
    except OSError:
        if tmp.is_file():
            tmp.unlink(missing_ok=True)
        raise


def _record_command_audio(duration_s: float = 2.0) -> sr.AudioData | None:
    try:
        with sd.InputStream(
            samplerate=SAMPLE_RATE,
            channels=1,
            dtype="int16",
            blocksize=1024,
        ) as stream:
            frames: list[np.ndarray] = []
            frames_recorded = 0
            total_frames = int(SAMPLE_RATE * duration_s)
            while frames_recorded < total_frames:
                read_frames = min(1024, total_frames - frames_recorded)
                data, overflowed = stream.read(read_frames)
                if overflowed:
                    log.warning("Input overflow while recording command.")
                frames.append(data.copy())
                frames_recorded += read_frames

        raw_data = np.concatenate(frames, axis=0).tobytes()
        return sr.AudioData(raw_data, SAMPLE_RATE, 2)
    except Exception as e:
        log.warning("Could not record command audio: %s", e)
        return None


def _get_whisper_model(model_name: str):
    if whisper is None:
        raise RuntimeError("whisper package not installed")
    if model_name not in _WHISPER_MODEL_CACHE:
        _WHISPER_MODEL_CACHE[model_name] = whisper.load_model(model_name)
    return _WHISPER_MODEL_CACHE[model_name]


def _recognize_with_whisper(audio_data: sr.AudioData) -> str | None:
    if whisper is None:
        return None
    try:
        wav_bytes = audio_data.get_wav_data(convert_rate=16000)
        with wave.open(io.BytesIO(wav_bytes), "rb") as wf:
            frames = wf.readframes(wf.getnframes())
            pcm = np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0
        model = _get_whisper_model(JARVIS_WHISPER_MODEL)
        result = model.transcribe(pcm, language="en", fp16=False)
        text = (result.get("text") or "").strip()
        return text or None
    except Exception as e:
        log.warning("Whisper recognition failed: %s", e)
        return None


def _recognize_command(audio_data: sr.AudioData) -> str | None:
    if JARVIS_STT_BACKEND in {"whisper", "local", "local-whisper"}:
        local_text = _recognize_with_whisper(audio_data)
        if local_text:
            return local_text

    recognizer = sr.Recognizer()
    try:
        text = recognizer.recognize_google(audio_data)
        return text
    except sr.UnknownValueError:
        log.info("Speech recognition could not understand audio.")
        return None
    except sr.RequestError as e:
        log.warning("Speech recognition request failed: %s", e)
        return None


def _normalize_text(text: str) -> str:
    return " ".join(text.lower().split())


def listen_for_command() -> str | None:
    log.info("Listening for a command. Please speak clearly now... Speak a short sentence near the mic.")
    audio_data = _record_command_audio(duration_s=2.0)
    if audio_data is not None:
        recognized = _recognize_command(audio_data)
        if recognized:
            return recognized

    return None


def _ask_ollama(prompt: str) -> str | None:
    """Query local Ollama instance for response."""
    if not OLLAMA_ENABLED:
        return None
    url = f"{OLLAMA_API_URL}/api/generate"
    body = {
        "model": OLLAMA_MODEL,
        "prompt": prompt,
        "temperature": OLLAMA_TEMPERATURE,
        "stream": False,
        "num_predict": 200,
    }
    payload = json.dumps(body).encode("utf-8")
    headers = {"Content-Type": "application/json; charset=utf-8"}
    try:
        request = urllib.request.Request(url, data=payload, headers=headers, method="POST")
        with urllib.request.urlopen(request, timeout=30) as response:
            data = json.load(response)
    except Exception as e:
        log.warning("Ollama API call failed: %s", e)
        return None

    response_text = data.get("response", "").strip()
    return response_text if response_text else None


def _open_spotify(query: str | None = None) -> None:
    log.info("Opening Spotify...")
    if query:
        search_url = "https://open.spotify.com/search/" + urllib.parse.quote(query)
        try:
            webbrowser.open(search_url)
            return
        except Exception as e:
            log.warning("Could not open Spotify search: %s", e)
    try:
        if sys.platform == "win32":
            os.startfile("spotify:")
            return
    except OSError:
        pass
    webbrowser.open("https://open.spotify.com")


def _open_youtube(query: str | None = None) -> None:
    log.info("Opening YouTube...")
    if query:
        cleaned = query.strip()
        if cleaned.lower().startswith("play "):
            cleaned = cleaned[5:].strip()
        if cleaned.lower().startswith("music "):
            cleaned = cleaned[6:].strip()
        url = "https://www.youtube.com/results?search_query=" + urllib.parse.quote(cleaned)
    else:
        url = "https://www.youtube.com"
    try:
        webbrowser.open(url)
    except Exception as e:
        log.warning("Could not open YouTube: %s", e)


def _open_youtube_music(query: str | None = None) -> None:
    log.info("Opening YouTube Music...")
    if query:
        url = "https://music.youtube.com/search?q=" + urllib.parse.quote(query)
    else:
        url = "https://music.youtube.com"
    try:
        webbrowser.open(url)
    except Exception as e:
        log.warning("Could not open YouTube Music: %s", e)


def _open_vscode() -> None:
    log.info("Opening VS Code...")
    code_bin = shutil.which("code")
    if code_bin:
        try:
            args = [code_bin]
            if JARVIS_WEBSITE_DIR:
                args.append(str(Path(JARVIS_WEBSITE_DIR).expanduser()))
            subprocess.Popen(
                args,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            return
        except OSError as e:
            log.warning("Could not launch VS Code: %s", e)
    try:
        if sys.platform == "win32":
            os.startfile("vscode:")
            return
    except OSError:
        pass
    log.warning("VS Code is not available on PATH and the vscode protocol is not registered.")


def _save_reminder_to_calendar(title: str, when_text: str | None = None) -> None:
    reminder_path = Path(__file__).resolve().parent / "session_state" / "reminders.txt"
    reminder_path.parent.mkdir(parents=True, exist_ok=True)
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{timestamp}] {title}"
    if when_text:
        line += f" | when: {when_text}"
    line += "\n"
    with reminder_path.open("a", encoding="utf-8") as fh:
        fh.write(line)
    log.info("Saved reminder to %s", reminder_path)
    say_text(f"I saved your reminder for {title}.")


def _parse_reminder_request(text: str) -> tuple[str | None, str | None]:
    cleaned = text.strip()
    if not cleaned:
        return None, None
    prefix = "reminder"
    if cleaned.lower().startswith(prefix):
        cleaned = cleaned[len(prefix):].strip()
    if not cleaned:
        return None, None
    title = None
    when_text = None
    for marker in (" for ", " at ", " on "):
        if marker in cleaned.lower():
            parts = cleaned.split(marker, 1)
            if len(parts) == 2:
                title = parts[0].strip().strip(" ,") or None
                when_text = parts[1].strip().strip(" ,") or None
                break
    if title is None:
        title = cleaned
    return title, when_text


def _build_website_project() -> None:
    if JARVIS_WEBSITE_BUILD_CMD:
        project_dir = Path(JARVIS_WEBSITE_DIR).expanduser() if JARVIS_WEBSITE_DIR else Path.cwd()
        if not project_dir.exists():
            say_text("I could not find the website project folder.")
            return
        log.info("Building website in %s with command: %s", project_dir, JARVIS_WEBSITE_BUILD_CMD)
        try:
            subprocess.Popen(
                JARVIS_WEBSITE_BUILD_CMD,
                cwd=str(project_dir),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                shell=True,
            )
            say_text("Building your website now.")
            return
        except OSError as e:
            log.warning("Could not run website build command: %s", e)
            say_text("I could not start the website build command.")
            return
    if JARVIS_WEBSITE_URL:
        log.info("Opening website URL: %s", JARVIS_WEBSITE_URL)
        webbrowser.open(JARVIS_WEBSITE_URL)
        say_text("Opening your website in the browser.")
        return
    say_text("I do not know how to build your website. Set JARVIS_WEBSITE_BUILD_CMD or JARVIS_WEBSITE_URL.")


def _respond_to_command(command: str | None, conversation_history: list[tuple[str, str]] | None = None) -> bool:
    if not command:
        say_text("I did not catch that. Please try again.")
        return True

    text = command.strip()
    low = text.lower()
    if "time" in low:
        say_text(f"The current time is {time.strftime('%I:%M %p')}")
    elif "date" in low:
        say_text(f"Today is {time.strftime('%A, %B %d, %Y')}")
    elif "hello" in low or "hi" in low:
        say_text("Hello. How can I help you today?")
    elif "open spotify" in low or low == "spotify":
        query = None
        if low.startswith("open spotify"):
            query = text[len("open spotify"):].strip()
        elif low.startswith("play "):
            query = text[5:].strip()
        if query:
            _open_spotify(query)
        else:
            _open_spotify()
    elif "youtube music" in low or "yt music" in low:
        query = text
        for prefix in ("open youtube music", "open yt music", "youtube music", "yt music"):
            if query.lower().startswith(prefix):
                query = query[len(prefix):].strip()
                break
        _open_youtube_music(query or None)
    elif "open youtube" in low or "youtube" in low:
        query = text
        for prefix in ("open youtube", "youtube"):
            if query.lower().startswith(prefix):
                query = query[len(prefix):].strip()
                break
        if "play" in low:
            query = query.replace("play", "", 1).strip()
        if query.strip():
            _open_youtube(query.strip())
        else:
            _open_youtube()
    elif "open vscode" in low or "open code" in low or "open visual studio code" in low:
        _open_vscode()
    elif "build website" in low or "open website" in low or "website" in low:
        _build_website_project()
    elif "open claude" in low or "claude" in low:
        say_text("I have already opened Claude for you.")
    elif "reminder" in low:
        title, when_text = _parse_reminder_request(text)
        if title:
            _save_reminder_to_calendar(title, when_text)
        else:
            say_text("I could not parse your reminder. Please say something like reminder call mom at 6 pm.")
    elif "stop" in low or "exit" in low or "quit" in low or "goodbye" in low:
        say_text("Stopping now. I will pause listening.")
        return False
    else:
        if conversation_history is not None:
            history_for_prompt = conversation_history[-4:]
            context_prompt = "\n".join(
                [f"User: {user}\nJarvis: {assistant}" for user, assistant in history_for_prompt]
            )
            prompt = f"{context_prompt}\nUser: {text}\nJarvis:"
        else:
            prompt = text
        ollama_response = _ask_ollama(prompt)
        if conversation_history is not None:
            conversation_history.append((text, ollama_response or ""))
        if ollama_response:
            say_text(ollama_response)
        else:
            say_text(f"You said: {text}. I am ready for your next command.")
    return True


def _command_loop() -> None:
    say_text("I am listening. Say stop when you want me to pause.")
    conversation_history: list[tuple[str, str]] = []
    while True:
        command = listen_for_command()
        if command is None:
            continue
        normalized_command = _normalize_text(command)
        if normalized_command in {"stop", "exit", "quit", "goodbye"}:
            say_text("Okay, I will pause listening now.")
            break
        if not _respond_to_command(command, conversation_history):
            break


def say_text(text: str) -> None:
    if not text.strip():
        return
    voice, rate, volume = edge_tts_env_config()
    cache_path = _jarvis_welcome_cache_path(text, voice, rate, volume)
    if JARVIS_WELCOME_CACHE_ENABLED and cache_path.is_file():
        if _play_pcm_wav_file(cache_path):
            return
    if voice:
        try:
            import edge_tts
        except ImportError:
            log.warning("Install dependencies: pip install -r requirements.txt")
        else:
            tmp_path = cache_path.with_suffix(".tmp.wav")
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            try:
                communicate = edge_tts.Communicate(text, voice=voice, rate=rate, volume=volume)
                asyncio.run(communicate.save(str(tmp_path)))
                if not tmp_path.is_file():
                    raise RuntimeError("Edge TTS did not produce audio file")
                if JARVIS_WELCOME_CACHE_ENABLED:
                    tmp_path.replace(cache_path)
                    playback_path = cache_path
                else:
                    playback_path = tmp_path
                if _play_pcm_wav_file(playback_path):
                    return
            except Exception as e:
                log.warning("Edge TTS failed: %s", e)
            finally:
                if not JARVIS_WELCOME_CACHE_ENABLED and tmp_path.is_file():
                    try:
                        tmp_path.unlink()
                    except OSError:
                        pass
    _speak_with_sapi(text)


def _speak_with_powershell(text: str) -> None:
    if sys.platform != "win32":
        return
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False, suffix=".txt") as tmp:
        tmp.write(text)
        tmp_path = tmp.name
    try:
        safe_path = tmp_path.replace("'", "''")
        subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-Command",
                f"Add-Type -AssemblyName System.Speech; $s = New-Object System.Speech.Synthesis.SpeechSynthesizer; $s.Speak((Get-Content -Raw -Path '{safe_path}'))",
            ],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except Exception as e:
        log.warning("PowerShell speech failed: %s", e)
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass


def _speak_with_sapi(text: str) -> None:
    if win32com_client is not None:
        try:
            speaker = win32com_client.Dispatch("SAPI.SpVoice")
            speaker.Speak(text)
            return
        except Exception as e:
            log.warning("SAPI speech failed: %s", e)
    _speak_with_powershell(text)


def say_jarvis_welcome() -> None:
    if not JARVIS_WELCOME_ENABLED or not JARVIS_WELCOME_PHRASE.strip():
        return
    text = JARVIS_WELCOME_PHRASE.strip()

    voice, rate, volume = edge_tts_env_config()
    cache_path = _jarvis_welcome_cache_path(text, voice, rate, volume)
    if JARVIS_WELCOME_CACHE_ENABLED and cache_path.is_file():
        log.info("Playing welcome from cache: %s", cache_path)
        if _play_pcm_wav_file(cache_path):
            return
        log.warning("Cache miss after read failure; deleting invalid cache and retrying.")
        try:
            cache_path.unlink(missing_ok=True)
        except OSError:
            pass

    if voice:
        try:
            import edge_tts
        except ImportError:
            log.warning("Install dependencies: pip install -r requirements.txt")
        else:
            tmp_path = cache_path.with_suffix(".tmp.wav")
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            try:
                communicate = edge_tts.Communicate(text, voice=voice, rate=rate, volume=volume)
                asyncio.run(communicate.save(str(tmp_path)))
                if not tmp_path.is_file():
                    raise RuntimeError("Edge TTS did not produce audio file")
                if JARVIS_WELCOME_CACHE_ENABLED:
                    tmp_path.replace(cache_path)
                    playback_path = cache_path
                    log.info("Saved welcome audio to cache: %s", cache_path)
                else:
                    playback_path = tmp_path
                if _play_pcm_wav_file(playback_path):
                    return
            except Exception as e:
                log.warning("Edge TTS failed: %s", e)
            finally:
                if not JARVIS_WELCOME_CACHE_ENABLED and tmp_path.is_file():
                    try:
                        tmp_path.unlink()
                    except OSError:
                        pass

    _speak_with_sapi(text)


def play_song(uri: str) -> None:
    u = uri.strip()
    if not u:
        return
    try:
        if sys.platform == "win32":
            os.startfile(u)
        else:
            webbrowser.open(u)
    except OSError as e:
        log.warning("Could not open SONG_URI: %s", e)


def _chrome_executable() -> str | None:
    if sys.platform == "win32":
        for base in (
            os.environ.get("ProgramFiles", r"C:\Program Files"),
            os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"),
            os.environ.get("LOCALAPPDATA", ""),
        ):
            if not base:
                continue
            p = os.path.join(base, "Google", "Chrome", "Application", "chrome.exe")
            if os.path.isfile(p):
                return p
    return shutil.which("google-chrome") or shutil.which("chrome")


def _win32_sorted_monitor_rects() -> list[tuple[int, int, int, int]]:
    """Each monitor as (left, top, right, bottom), sorted left-to-right then top-to-bottom."""
    if sys.platform != "win32":
        return []
    import ctypes
    from ctypes import wintypes

    class RECT(ctypes.Structure):
        _fields_ = [
            ("left", wintypes.LONG),
            ("top", wintypes.LONG),
            ("right", wintypes.LONG),
            ("bottom", wintypes.LONG),
        ]

    collected: list[tuple[int, int, int, int]] = []

    @ctypes.WINFUNCTYPE(
        wintypes.BOOL,
        wintypes.HMONITOR,
        wintypes.HDC,
        ctypes.POINTER(RECT),
        wintypes.LPARAM,
    )
    def _cb(_hm, _hdc, lprc, _lp):
        r = lprc.contents
        collected.append((int(r.left), int(r.top), int(r.right), int(r.bottom)))
        return True

    ctypes.windll.user32.EnumDisplayMonitors(None, None, _cb, 0)
    collected.sort(key=lambda t: (t[0], t[1]))
    return collected


def _chrome_monitor_top_left(one_based_index: int) -> tuple[int, int]:
    """Top-left corner on virtual desktop for monitor N (1-based)."""
    l, t, _, _ = _chrome_monitor_bounds(one_based_index)
    return (l, t)


def _chrome_monitor_bounds(one_based_index: int) -> tuple[int, int, int, int]:
    """Monitor N as (left, top, right, bottom), 1-based index (sorted like other Chrome helpers)."""
    rects = _win32_sorted_monitor_rects()
    if not rects:
        return (0, 0, 1920, 1080)
    idx = one_based_index - 1
    if idx < 0:
        idx = 0
    if idx >= len(rects):
        log.warning(
            "Monitor %d requested but only %d found; using last monitor.",
            one_based_index,
            len(rects),
        )
        idx = len(rects) - 1
    return rects[idx]


def _chrome_monitor_pixel_size(one_based_index: int) -> tuple[int, int]:
    l, t, r, b = _chrome_monitor_bounds(one_based_index)
    return (max(320, r - l), max(240, b - t))


def _chrome_window_size() -> tuple[int, int]:
    w = (os.environ.get("CHROME_WINDOW_WIDTH") or "1400").strip()
    h = (os.environ.get("CHROME_WINDOW_HEIGHT") or "900").strip()
    try:
        return (max(400, int(w)), max(300, int(h)))
    except ValueError:
        return (1400, 900)


def _chrome_site_user_data_dir(site_key: str) -> str:
    p = Path(tempfile.gettempdir()) / "clap-trigger-chrome" / site_key
    p.mkdir(parents=True, exist_ok=True)
    return str(p)


def _chrome_new_window_wait_timeout_s() -> float:
    try:
        return max(3.0, float((os.environ.get("CHROME_NEW_WINDOW_WAIT_S") or "25").strip()))
    except ValueError:
        return 25.0


def _chrome_top_level_browser_hwnds_win32() -> set[int]:
    """HWND ints for visible-or-minimized top-level Chrome browser windows."""
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32
    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    GW_OWNER = 4
    GWL_EXSTYLE = -20
    WS_EX_TOOLWINDOW = 0x00000080
    found: set[int] = set()

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def _enum(hwnd: wintypes.HWND, _lp: wintypes.LPARAM) -> bool:
        if user32.GetWindow(hwnd, GW_OWNER):
            return True
        if user32.GetWindowLongW(hwnd, GWL_EXSTYLE) & WS_EX_TOOLWINDOW:
            return True
        if not user32.IsWindowVisible(hwnd) and not user32.IsIconic(hwnd):
            return True
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if pid.value == 0:
            return True
        hproc = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid.value)
        if not hproc:
            return True
        try:
            buf = ctypes.create_unicode_buffer(4096)
            sz = wintypes.DWORD(len(buf))
            if not kernel32.QueryFullProcessImageNameW(hproc, 0, buf, ctypes.byref(sz)):
                return True
            exe_path = buf.value
        finally:
            kernel32.CloseHandle(hproc)
        if os.path.basename(exe_path).lower() != "chrome.exe":
            return True
        r = wintypes.RECT()
        if not user32.GetWindowRect(hwnd, ctypes.byref(r)):
            return True
        w, h = r.right - r.left, r.bottom - r.top
        if w < 80 or h < 80:
            return True
        found.add(int(hwnd))
        return True

    user32.EnumWindows(_enum, 0)
    return found


def _wait_new_chrome_hwnd_win32(before: set[int], timeout: float) -> int | None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        time.sleep(0.12)
        now = _chrome_top_level_browser_hwnds_win32()
        new = now - before
        if not new:
            continue
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.windll.user32
        best: int | None = None
        best_area = 0
        for h in new:
            r = wintypes.RECT()
            if user32.GetWindowRect(h, ctypes.byref(r)):
                a = max(0, r.right - r.left) * max(0, r.bottom - r.top)
                if a > best_area:
                    best_area = a
                    best = h
        if best is not None:
            return best
    return None


def _chrome_snap_window_to_monitor_win32(
    hwnd: int,
    one_based_monitor: int,
    *,
    fullscreen: bool,
    windowed_size: tuple[int, int] | None,
) -> None:
    import ctypes
    from ctypes import wintypes

    ml, mt, mr, mb = _chrome_monitor_bounds(one_based_monitor)
    user32 = ctypes.windll.user32
    SW_RESTORE = 9
    SW_SHOWMAXIMIZED = 3
    HWND_TOP = 0
    SWP_SHOWWINDOW = 0x0040
    SWP_FRAMECHANGED = 0x0020
    flags = SWP_SHOWWINDOW | SWP_FRAMECHANGED

    user32.ShowWindow(hwnd, SW_RESTORE)
    if fullscreen:
        w, h = mr - ml, mb - mt
        x, y = ml, mt
    else:
        ww, wh = windowed_size or _chrome_window_size()
        w, h = ww, wh
        x = ml + max(0, (mr - ml - w) // 2)
        y = mt + max(0, (mb - mt - h) // 2)
    user32.SetWindowPos(hwnd, HWND_TOP, x, y, w, h, flags)

    if fullscreen:
        user32.ShowWindow(hwnd, SW_SHOWMAXIMIZED)
        KEYEVENTF_KEYUP = 0x0002
        VK_F11 = 0x7A
        fg = user32.GetForegroundWindow()
        tid_tgt = user32.GetWindowThreadProcessId(hwnd, None)
        tid_fg = user32.GetWindowThreadProcessId(fg, None) if fg else 0
        if tid_fg and tid_tgt:
            user32.AttachThreadInput(tid_fg, tid_tgt, True)
        user32.SetForegroundWindow(hwnd)
        if tid_fg and tid_tgt:
            user32.AttachThreadInput(tid_fg, tid_tgt, False)
        user32.keybd_event(VK_F11, 0, 0, 0)
        user32.keybd_event(VK_F11, 0, KEYEVENTF_KEYUP, 0)


def _open_url_in_chrome(
    url: str,
    *,
    new_window: bool = True,
    label: str = "URL",
    window_position: tuple[int, int] | None = None,
    window_size: tuple[int, int] | None = None,
    fullscreen: bool = False,
    win32_post_fullscreen_monitor: int | None = None,
    user_data_dir: str | None = None,
) -> None:
    u = url.strip()
    if not u:
        return
    chrome = _chrome_executable()
    try:
        if chrome:
            args = [chrome]
            if user_data_dir:
                args.append(f"--user-data-dir={user_data_dir}")
                args.append("--no-first-run")
            if new_window:
                args.append("--new-window")
            if window_position is not None:
                x, y = window_position
                args.append(f"--window-position={x},{y}")
            if window_size:
                args.append(f"--window-size={window_size[0]},{window_size[1]}")
            if fullscreen and not (
                sys.platform == "win32" and win32_post_fullscreen_monitor is not None
            ):
                args.append("--start-fullscreen")
            args.append(u)
            popen_kw: dict = {
                "args": args,
                "stdin": subprocess.DEVNULL,
                "stdout": subprocess.DEVNULL,
                "stderr": subprocess.DEVNULL,
            }
            if sys.platform == "win32":
                popen_kw["creationflags"] = subprocess.CREATE_NO_WINDOW
            before: set[int] | None = None
            if sys.platform == "win32" and win32_post_fullscreen_monitor is not None:
                before = _chrome_top_level_browser_hwnds_win32()
            subprocess.Popen(**popen_kw)
            if sys.platform == "win32" and win32_post_fullscreen_monitor is not None:
                mon = win32_post_fullscreen_monitor
                hwnd = _wait_new_chrome_hwnd_win32(before, _chrome_new_window_wait_timeout_s())
                if hwnd is not None:
                    _chrome_snap_window_to_monitor_win32(
                        hwnd,
                        mon,
                        fullscreen=fullscreen,
                        windowed_size=window_size if not fullscreen else None,
                    )
                else:
                    log.warning(
                        "Chrome: timed out waiting for new window (%s); check "
                        "CHROME_NEW_WINDOW_WAIT_S or close extra Chrome instances.",
                        label,
                    )
        else:
            log.warning("Chrome not found; opening %s in default browser.", label)
            webbrowser.open(u)
    except OSError as e:
        log.warning("Could not open %s in Chrome: %s", label, e)


def open_claude_in_chrome() -> None:
    if not OPEN_CLAUDE_CODE_IN_CHROME:
        return
    url = (os.environ.get("CLAUDE_CODE_URL") or "https://claude.ai/new").strip()
    pos: tuple[int, int] | None = None
    size: tuple[int, int] | None = None
    fs = OPEN_CHROME_FULLSCREEN
    post_mon: int | None = None
    user_data: str | None = None
    if sys.platform == "win32":
        post_mon = CLAUDE_CHROME_MONITOR
        pos = _chrome_monitor_top_left(CLAUDE_CHROME_MONITOR)
        if fs:
            size = _chrome_monitor_pixel_size(CLAUDE_CHROME_MONITOR)
        else:
            size = _chrome_window_size()
        if CHROME_SEPARATE_SITE_PROFILES:
            user_data = _chrome_site_user_data_dir("claude")
    elif not fs:
        size = _chrome_window_size()
    else:
        size = None
    _open_url_in_chrome(
        url,
        new_window=True,
        label="Claude",
        window_position=pos,
        window_size=size,
        fullscreen=fs,
        win32_post_fullscreen_monitor=post_mon,
        user_data_dir=user_data,
    )


def _cursor_executable() -> str | None:
    if sys.platform == "win32":
        local = os.environ.get("LOCALAPPDATA", "")
        for sub in ("Programs\\cursor\\Cursor.exe", "Programs\\Cursor\\Cursor.exe"):
            if local:
                p = os.path.join(local, *sub.split("\\"))
                if os.path.isfile(p):
                    return p
    return shutil.which("cursor")


def _cursor_largest_main_hwnd_win32() -> int | None:
    """Largest top-level Cursor.exe window (visible or minimized)."""
    if sys.platform != "win32":
        return None
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32
    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    GW_OWNER = 4
    GWL_EXSTYLE = -20
    WS_EX_TOOLWINDOW = 0x00000080
    candidates: list[tuple[int, wintypes.HWND]] = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def _enum(hwnd: wintypes.HWND, _lp: wintypes.LPARAM) -> bool:
        if user32.GetWindow(hwnd, GW_OWNER):
            return True
        if user32.GetWindowLongW(hwnd, GWL_EXSTYLE) & WS_EX_TOOLWINDOW:
            return True
        if not user32.IsWindowVisible(hwnd) and not user32.IsIconic(hwnd):
            return True
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if pid.value == 0:
            return True
        hproc = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid.value)
        if not hproc:
            return True
        try:
            buf = ctypes.create_unicode_buffer(4096)
            sz = wintypes.DWORD(len(buf))
            if not kernel32.QueryFullProcessImageNameW(hproc, 0, buf, ctypes.byref(sz)):
                return True
            exe_path = buf.value
        finally:
            kernel32.CloseHandle(hproc)
        if os.path.basename(exe_path).lower() != "cursor.exe":
            return True
        r = wintypes.RECT()
        if not user32.GetWindowRect(hwnd, ctypes.byref(r)):
            return True
        w, h = r.right - r.left, r.bottom - r.top
        if w < 200 or h < 200:
            return True
        candidates.append((w * h, hwnd))
        return True

    user32.EnumWindows(_enum, 0)
    if not candidates:
        return None
    return int(max(candidates, key=lambda t: t[0])[1])


def _cursor_foreground_hwnd_win32(hwnd: int) -> None:
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32
    SW_RESTORE = 9
    user32.ShowWindow(hwnd, SW_RESTORE)
    fg = user32.GetForegroundWindow()
    tid_tgt = user32.GetWindowThreadProcessId(hwnd, None)
    tid_fg = user32.GetWindowThreadProcessId(fg, None) if fg else 0
    if tid_fg and tid_tgt:
        user32.AttachThreadInput(tid_fg, tid_tgt, True)
    user32.SetForegroundWindow(hwnd)
    if tid_fg and tid_tgt:
        user32.AttachThreadInput(tid_fg, tid_tgt, False)


def _cursor_send_f11_fullscreen_win32(hwnd: int) -> None:
    """F11 toggles Zen/fullscreen in Cursor (Electron)."""
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32
    KEYEVENTF_KEYUP = 0x0002
    VK_F11 = 0x7A
    _cursor_foreground_hwnd_win32(hwnd)
    user32.keybd_event(VK_F11, 0, 0, 0)
    user32.keybd_event(VK_F11, 0, KEYEVENTF_KEYUP, 0)


def _focus_existing_cursor_window_win32() -> bool:
    """Bring an existing Cursor.exe main window to the foreground (no new process)."""
    if sys.platform != "win32":
        return False
    hwnd = _cursor_largest_main_hwnd_win32()
    if hwnd is None:
        return False
    _cursor_foreground_hwnd_win32(hwnd)
    return True


def run_double_clap_actions() -> None:
    """Run outside the mic loop so sleeps do not stall capture."""
    play_song(SONG_URI)
    open_claude_in_chrome()
    if JARVIS_WELCOME_ENABLED and JARVIS_WELCOME_PHRASE.strip():
        delay = max(0.0, JARVIS_AFTER_SONG_DELAY_S)
        if delay:
            time.sleep(delay)
        say_jarvis_welcome()
    _command_loop()


def open_cursor_window() -> None:
    if not FOCUS_EXISTING_CURSOR_ON_DOUBLE_CLAP and not OPEN_NEW_CURSOR_ON_DOUBLE_CLAP:
        return
    exe = _cursor_executable()
    if not exe:
        log.warning(
            "Could not find Cursor (install app or add the `cursor` command to PATH)."
        )
        return
    popen_kw: dict = {
        "stdin": subprocess.DEVNULL,
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
    }
    if sys.platform == "win32":
        popen_kw["creationflags"] = subprocess.CREATE_NO_WINDOW
    try:
        if FOCUS_EXISTING_CURSOR_ON_DOUBLE_CLAP:
            focused = (
                sys.platform == "win32" and _focus_existing_cursor_window_win32()
            )
            if not focused:
                subprocess.Popen([exe], **popen_kw)
        if OPEN_NEW_CURSOR_ON_DOUBLE_CLAP:
            subprocess.Popen([exe, "-n"], **popen_kw)
    except OSError as e:
        log.warning("Could not start or focus Cursor: %s", e)
        return
    if sys.platform == "win32" and CURSOR_OPEN_FULLSCREEN:
        time.sleep(0.5)
        hwnd = _cursor_largest_main_hwnd_win32()
        if hwnd is not None:
            _cursor_send_f11_fullscreen_win32(hwnd)
        else:
            log.warning("Cursor fullscreen: no Cursor window found to send F11.")


def main() -> int:
    blocksize = block_samples()
    noise_floor = 1e-4
    last_logged_double = 0.0
    first_clap_time: float | None = None
    spike_armed = True
    welcome_sequence_done = False

    log.info(
        "Listening (double clap: %.2f–%.2fs apart, rate=%d, block=%d ms, "
        "spike_ratio=%.1f, cooldown=%.2fs). Ctrl+C to stop.",
        MIN_DOUBLE_GAP_S,
        MAX_DOUBLE_GAP_S,
        SAMPLE_RATE,
        BLOCK_MS,
        SPIKE_RATIO,
        COOLDOWN_S,
    )
    if SONG_URI.strip():
        log.info("Double clap opens this track: %s", SONG_URI.strip())
    else:
        log.info("SONG_URI is empty — set it to play one song on each double clap.")
    if OPEN_CLAUDE_CODE_IN_CHROME:
        cu = (os.environ.get("CLAUDE_CODE_URL") or "https://claude.ai/new").strip()
        log.info(
            "After Spotify, open Claude in Chrome%s on monitor %d: %s",
            " fullscreen" if OPEN_CHROME_FULLSCREEN else "",
            CLAUDE_CHROME_MONITOR,
            cu,
        )
    if OPEN_CLAUDE_CODE_IN_CHROME:
        cu = (os.environ.get("CLAUDE_CODE_URL") or "https://claude.ai/new").strip()
        log.info(
            "After Spotify, open Claude in Chrome%s on monitor %d: %s",
            " fullscreen" if OPEN_CHROME_FULLSCREEN else "",
            CLAUDE_CHROME_MONITOR,
            cu,
        )
    if JARVIS_WELCOME_ENABLED:
        ev, er, el = edge_tts_env_config()
        log.info(
            "After song + %.2fs: %r (Edge TTS voice=%s, rate=%s, volume=%s)",
            JARVIS_AFTER_SONG_DELAY_S,
            JARVIS_WELCOME_PHRASE.strip(),
            ev or "(unset)",
            er,
            el,
        )

    if JARVIS_WAKE_MODE == "typed":
        log.info("Using typed-command mode; skipping microphone wake loop.")
        try:
            _command_loop()
        except KeyboardInterrupt:
            log.info("Stopped.")
            return 0
        return 0

    input_idx = _choose_input_device(blocksize)

    try:
        with sd.InputStream(
            device=input_idx,
            samplerate=SAMPLE_RATE,
            channels=CHANNELS,
            dtype="float32",
            blocksize=blocksize,
        ) as stream:
            while True:
                data, overflowed = stream.read(blocksize)
                if overflowed:
                    log.warning("Input overflow; try a larger BLOCK_MS")

                level = rms_mono(data)

                quiet_gate = noise_floor * QUIET_GATE_MULT
                if level < quiet_gate:
                    noise_floor = NOISE_FLOOR_ALPHA * noise_floor + (
                        1.0 - NOISE_FLOOR_ALPHA
                    ) * level
                    noise_floor = max(noise_floor, 1e-7)

                threshold = max(noise_floor * SPIKE_RATIO, MIN_RMS)
                now = time.monotonic()
                retrigger_level = threshold * RETRIGGER_RATIO

                if level < retrigger_level:
                    spike_armed = True

                if (
                    spike_armed
                    and level >= threshold
                    and (now - last_logged_double) >= COOLDOWN_S
                ):
                    spike_armed = False
                    if first_clap_time is None:
                        first_clap_time = now
                    else:
                        gap = now - first_clap_time
                        if gap < MIN_DOUBLE_GAP_S:
                            pass
                        elif gap <= MAX_DOUBLE_GAP_S:
                            first_clap_time = None
                            last_logged_double = now
                            if not welcome_sequence_done:
                                welcome_sequence_done = True
                                log.info(
                                    "Double clap detected (gap=%.3fs, rms=%.5f, "
                                    "noise_floor=%.5f, threshold=%.5f) — running welcome once",
                                    gap,
                                    level,
                                    noise_floor,
                                    threshold,
                                )
                                threading.Thread(
                                    target=run_double_clap_actions, daemon=True
                                ).start()
                        else:
                            first_clap_time = now

    except KeyboardInterrupt:
        log.info("Stopped.")
        return 0
    except sd.PortAudioError as e:
        log.error("Audio error: %s", e)
        log.error("If PortAudio fails, install/repair drivers or try another SAMPLE_RATE.")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
