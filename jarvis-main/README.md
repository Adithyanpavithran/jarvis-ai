# Jarvis Desktop AI Assistant

Jarvis is a modular, production-grade local desktop AI assistant for Windows built with **Python**, **Ollama**, and **PySide6** (Qt for Python). It runs entirely on your local machine, keeping your data secure while providing deep integration into your desktop system.

## Project Architecture

The project is structured under a clean architecture system:

```
jarvis/
  app/
    config/          # Configuration schema, registry entry, settings manager
    database/        # SQLite backend (memory storage, conversations history, note, todo)
    voice/           # Speech-To-Text (Whisper), Text-To-Speech (Edge, SAPI), Wake Word
    ai/              # Ollama client connection, system prompts, tool execution parser
    automation/      # Native system control, file system operations, media player control
    plugins/         # Custom dynamic plugin loaders
    ui/              # PySide6 widgets: floating assistant, animated pulse, dashboard tabs
    utils/           # Rotational loggers, dynamic directory resolvers
    main.py          # Entry point, background VoiceWorker thread, system tray menu
  plugins/           # Dynamic custom drop-in user plugins directory
  requirements.txt   # Package dependencies
  README.md          # User documentation
```

---

## Features

1. **Floating Glow Widget**: A circular widget that floats above all apps. Pulsates to indicate state:
   - **Cyan (Breathe)**: Idle / Listening for Wake Word.
   - **Pink (Pulse)**: Listening for speech.
   - **Orange (Shimmer)**: Querying local LLM (thinking).
   - **Purple (Wave)**: Speaking responses.
2. **Settings Window**: Configure TTS voice/rate, wake mode, STT models, and local Ollama parameters.
3. **Continuous Microphone Monitoring**: Speech activity auto-calibration stops recording 1.2s after silence.
4. **SQLite Memory Manager**: Retains semantic memories and user profile facts used in LLM context.
5. **Dynamic Tool Calling**: Recognizes commands and triggers desktop actions (volume, screenshots, app opening, lock screen).
6. **Task Board**: Built-in To-Do list manager connected directly to database commands.

---

## Installation & Setup

### Prerequisites

1. Install **Python 3.10 to 3.13**.
2. Install **Ollama** from [ollama.com](https://ollama.com).
3. Open your terminal and pull a model (e.g. Mistral):
   ```bash
   ollama pull mistral
   ```

### Setup Steps

1. Clone or copy this repository directory.
2. Open a PowerShell/cmd prompt in the directory and install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Run the application:
   ```bash
   python app/main.py
   ```

---

## Configuration & Customization

- Settings are saved to `%APPDATA%/Jarvis/settings.json`.
- Logs are kept in `%APPDATA%/Jarvis/logs/jarvis.log` with a 10MB rotation count.
- You can create drop-in plugins by writing python modules inheriting from `JarvisPlugin` and putting them in the `%APPDATA%/Jarvis/plugins/` directory. A sample plugin template `sample_plugin.py` is generated automatically at startup.
