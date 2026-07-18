# Desktop clap → Jarvis-style welcome

Python script that listens to your default microphone and runs a **double-clap** welcome flow (Spotify, Chrome windows, Edge TTS, Cursor). See constants at the top of `jarvis.py` for behavior and tuning.

## Setup

From this project directory:

```bash
python -m pip install -r requirements.txt
```

## Environment variables

The script loads a **`.env` file** in the same folder as `jarvis.py` (via `python-dotenv`). You can also set variables in the shell.

### Required (Edge TTS welcome line)

| Variable | Purpose |
| -------- | ------- |
| `EDGE_TTS_VOICE` | Voice name for Edge TTS, e.g. `en-US-JennyNeural`. |

Without this, the welcome speech is skipped (other actions may still run).

### Optional

| Variable | Purpose |
| -------- | ------- |
| `EDGE_TTS_RATE` | Speech rate, e.g. `0%`, `+10%`, `-10%`. Default is `0%`. |
| `EDGE_TTS_VOLUME` | Volume adjustment, e.g. `0%`, `+10%`, `-10%`. Default is `0%`. |
| `JARVIS_WELCOME_CACHE_DIR` | Custom folder for cached welcome WAV (default: `.cache/jarvis_welcome/` under the project). |
| `JARVIS_INPUT_DEVICE` | Optional mic override: **integer** index or **substring** of the device name. If unset, the script uses the Windows default; when that mic is silent, it auto-picks the loudest working input. List devices: `python -c "import sounddevice as sd; print(sd.query_devices())"`. |
| `CLAUDE_CODE_URL` | URL opened for Claude in Chrome (default: new chat). |
| `TASARADAR_URL` | URL opened for Tasaradar in Chrome (default: `https://tasaradar.com`). `BINANCE_BTC_URL` is still read as a fallback if set. |
| `CHROME_NEW_WINDOW_WAIT_S` | Seconds to wait for a new Chrome window on Windows (default `25`). |
| `CHROME_WINDOW_WIDTH` / `CHROME_WINDOW_HEIGHT` | Windowed Chrome size when not fullscreen. |

Example `.env`:

```env
EDGE_TTS_VOICE=en-US-JennyNeural
EDGE_TTS_RATE=+0%
EDGE_TTS_VOLUME=+0%
```

## Run

```bash
python jarvis.py
```

Allow the microphone if Windows prompts you. Stop with **Ctrl+C**.

## Tuning

Edit the constants at the top of `jarvis.py`:

| Constant      | Effect                                                            |
| ------------- | ----------------------------------------------------------------- |
| `SPIKE_RATIO` | Increase if you get false triggers; decrease if claps are missed. |
| `COOLDOWN_S`  | Minimum time between two logged claps.                            |
| `BLOCK_MS`    | Larger = slightly less CPU, a bit less precise timing.            |
| `MIN_RMS`     | Floor on how loud a block must be (helps in very quiet rooms).  |
| `SAMPLE_RATE` | Try `48000` if your device does not like `44100`.                 |

## Troubleshooting

- **Wrong or quiet mic:** On startup the script probes your default Windows input. If it is silent, it **auto-selects** the loudest working mic. To force a specific device, set `JARVIS_INPUT_DEVICE` in `.env` (index or name substring from `sounddevice.query_devices()`).
- **PortAudio / audio errors:** Update audio drivers or try another `SAMPLE_RATE`.
- **No reaction to claps:** Lower `SPIKE_RATIO` slightly or speak/clap closer to the mic.
- **Spam logs:** Raise `SPIKE_RATIO` or `COOLDOWN_S`.
- **No welcome speech:** Set `EDGE_TTS_VOICE` in `.env` and restart the terminal so variables load.

## Optional: Local Ollama LLM (free local models)

This project can use a local Ollama server for LLM responses (no cloud billing). By default `jarvis.py` will attempt to query `OLLAMA_API_URL` when `OLLAMA_ENABLED` is true (defaults to `http://localhost:11434`).

Quick steps:

1. Install Ollama for your platform (see the official Ollama instructions).
2. Pull a model you want to use (example `mistral`):

```bash
ollama pull mistral
```

3. Verify the server and available models:

```bash
python setup_ollama.py --check-server
python setup_ollama.py --list
```

4. Run Jarvis (ensure `OLLAMA_ENABLED=True` in `.env` if you want responses):

```bash
python jarvis.py
```

If you'd like a helper to pull models or check your local Ollama server, use the included script: [setup_ollama.py](setup_ollama.py).
