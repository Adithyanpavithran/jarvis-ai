import os
import sys
import time
import queue
import threading
import sounddevice as sd
import numpy as np
import speech_recognition as sr
from pathlib import Path

from PySide6.QtCore import QThread, Signal, Slot, Qt
from PySide6.QtGui import QIcon, QAction
from PySide6.QtWidgets import QApplication, QSystemTrayIcon, QMenu

# Setup path to resolve local imports correctly
sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.utils.logger import log
from app.config.settings import settings_manager
from app.database.db_manager import db_manager
from app.voice.wake_word import WakeWordDetector
from app.voice.stt import stt_manager
from app.voice.tts import tts_manager
from app.ai.ollama_client import ollama_client
from app.ai.tool_calls import tool_registry
import app.automation  # Triggers tool registrations
from app.ui.main_window import MainWindow
from app.ui.floating_widget import FloatingAssistant
from app.plugins.plugin_manager import plugin_manager


class VoiceWorker(QThread):
    state_changed = Signal(str)  # "idle", "listening", "thinking", "speaking"
    response_received = Signal(str, str)  # sender, message
    create_note_requested = Signal()
    create_task_requested = Signal()

    def __init__(self):
        super().__init__()
        self.running = True
        self.input_queue = queue.Queue()
        self.wake_detector = WakeWordDetector()
        self.state = "idle"
        self.processing_thread = None
        self.interrupted = False
        self.trigger_voice_record_once = False

    def stop(self):
        self.running = False
        self.input_queue.put(None)

    def submit_command(self, text: str):
        """Submit a typed command from the GUI."""
        self.input_queue.put(text)

    def set_state(self, state: str):
        self.state = state
        self.state_changed.emit(state)

    def run(self):
        log.info("Background Voice Worker thread started.")
        self.set_state("idle")
        
        SAMPLE_RATE = 44100
        while self.running:
            # Check for typed commands in queue first
            try:
                typed_cmd = self.input_queue.get_nowait()
                if typed_cmd is None:  # stop signal
                    break
                self.handle_command(typed_cmd, is_voice=False)
                continue
            except queue.Empty:
                pass

            wake_mode = settings_manager.get("wake_mode", "voice")

            # If not in voice/double_clap mode, sleep and skip mic listening
            if wake_mode not in ("voice", "double_clap"):
                time.sleep(0.1)
                continue

            # Open continuous microphone input stream
            try:
                with sd.InputStream(
                    samplerate=SAMPLE_RATE,
                    channels=1,
                    dtype="int16",
                    blocksize=1024,
                ) as stream:
                    log.info("Continuous mic stream opened successfully.")
                    
                    frames = []
                    speech_detected = False
                    silence_start_time = None
                    silence_limit = settings_manager.get("silence_limit", 0.8)
                    baseline_rms = 100.0
                    frames_recorded = 0
                    max_frames = int(SAMPLE_RATE * 5.0)

                    # Double clap variables
                    noise_floor = 1e-4
                    last_logged_double = 0.0
                    first_clap_time = None
                    spike_armed = True

                    while self.running:
                        # Interrupt loop if typed input arrives or mode changes
                        if not self.input_queue.empty():
                            break
                        
                        current_mode = settings_manager.get("wake_mode", "voice")
                        if current_mode not in ("voice", "double_clap"):
                            break

                        data, overflowed = stream.read(1024)
                        
                        # Check if we should process voice listening or double-clap detection
                        run_voice = (current_mode == "voice") or self.trigger_voice_record_once
                        
                        if not run_voice:
                            # Double-clap detection logic
                            block = data.flatten().astype(np.float32) / 32768.0
                            level = np.sqrt(np.mean(block**2)) if block.size > 0 else 0.0
                            
                            QUIET_GATE_MULT = 2.2
                            NOISE_FLOOR_ALPHA = 0.992
                            SPIKE_RATIO = 7.0
                            MIN_RMS = 0.012
                            RETRIGGER_RATIO = 0.55
                            MIN_DOUBLE_GAP_S = 0.05
                            MAX_DOUBLE_GAP_S = 0.35
                            COOLDOWN_S = 0.45
                            
                            quiet_gate = noise_floor * QUIET_GATE_MULT
                            if level < quiet_gate:
                                noise_floor = NOISE_FLOOR_ALPHA * noise_floor + (1.0 - NOISE_FLOOR_ALPHA) * level
                                noise_floor = max(noise_floor, 1e-7)
                                
                            threshold = max(noise_floor * SPIKE_RATIO, MIN_RMS)
                            now = time.monotonic()
                            retrigger_level = threshold * RETRIGGER_RATIO
                            
                            if level < retrigger_level:
                                spike_armed = True
                                
                            if spike_armed and level >= threshold and (now - last_logged_double) >= COOLDOWN_S:
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
                                        log.info("Double clap detected (gap=%.3fs, rms=%.5f, noise_floor=%.5f, threshold=%.5f)", gap, level, noise_floor, threshold)
                                        self.trigger_double_clap_actions()
                                    else:
                                        first_clap_time = now
                            continue

                        # Voice recording/listening logic
                        rms = np.sqrt(np.mean(data.astype(np.float32) ** 2)) if data.size > 0 else 0
                        
                        now_s = frames_recorded / SAMPLE_RATE
                        
                        # Continuous adaptive noise floor tracking when not speaking
                        speech_threshold = max(baseline_rms * 2.2, 150.0)

                        if not speech_detected:
                            # Slide window of pre-speech blocks to capture onset
                            if len(frames) > 3:
                                frames.pop(0)
                            frames.append(data.copy())

                            if rms > speech_threshold:
                                speech_detected = True
                                if self.state == "idle":
                                    self.set_state("listening")
                                log.info("Continuous Voice: Speech activity detected. Threshold: %.1f, RMS: %.1f", speech_threshold, rms)
                                frames_recorded = len(frames) * 1024
                            else:
                                # Slowly adapt baseline RMS to ambient noise level when not speaking
                                baseline_rms = 0.96 * baseline_rms + 0.04 * rms
                        else:
                            frames.append(data.copy())
                            frames_recorded += 1024
                            now_s = frames_recorded / SAMPLE_RATE

                            if rms < speech_threshold:
                                if silence_start_time is None:
                                    silence_start_time = now_s
                                elif now_s - silence_start_time >= silence_limit:
                                    log.info("Continuous Voice: Silence detected. Processing...")
                                    if self.state in ("idle", "listening"):
                                        self.set_state("thinking")
                                    
                                    raw_data = np.concatenate(frames, axis=0).tobytes()
                                    audio_data = sr.AudioData(raw_data, SAMPLE_RATE, 2)
                                    text = stt_manager.transcribe(audio_data)
                                    if text:
                                        self.handle_command(text, is_voice=True)
                                    
                                    # Reset state
                                    frames = []
                                    speech_detected = False
                                    silence_start_time = None
                                    frames_recorded = 0
                                    
                                    # Reset voice override flag to return to double-clap mode
                                    self.trigger_voice_record_once = False
                                    
                                    if self.state in ("listening", "thinking"):
                                        self.set_state("idle")
                            else:
                                silence_start_time = None

                            # Cut off long speech
                            if frames_recorded >= max_frames:
                                log.info("Continuous Voice: Max speech limit reached. Processing...")
                                if self.state in ("idle", "listening"):
                                    self.set_state("thinking")
                                
                                raw_data = np.concatenate(frames, axis=0).tobytes()
                                audio_data = sr.AudioData(raw_data, SAMPLE_RATE, 2)
                                text = stt_manager.transcribe(audio_data)
                                if text:
                                    self.handle_command(text, is_voice=True)
                                
                                frames = []
                                speech_detected = False
                                silence_start_time = None
                                frames_recorded = 0
                                
                                # Reset voice override flag to return to double-clap mode
                                self.trigger_voice_record_once = False
                                
                                if self.state in ("listening", "thinking"):
                                    self.set_state("idle")

            except Exception as e:
                log.error("Continuous mic stream error: %s. Reconnecting in 2s...", e)
                time.sleep(2.0)

    def is_stop_command(self, text: str) -> bool:
        clean = text.lower().strip().rstrip(".?!")
        if any(x in clean for x in ("youtube", "yt", "music", "spotify")):
            return False
        stop_phrases = ["stop", "cancel", "shut up", "quiet", "stop jarvis", "hold on", "never mind"]
        return any(phrase == clean or clean.startswith(phrase) for phrase in stop_phrases)

    def handle_command(self, text: str, is_voice: bool = False):
        """Handle incoming command, checking if it is a stop command or a new query."""
        if self.is_stop_command(text):
            log.info("Stop command detected: '%s'. Interrupting current processing.", text)
            self.interrupt_processing()
            return

        is_busy = self.processing_thread is not None and self.processing_thread.is_alive()

        # If it is a voice command and we are currently speaking, ignore it to prevent feedback loop
        if is_voice and is_busy and self.state == "speaking":
            log.info("Ignoring voice command '%s' since assistant is currently speaking.", text)
            return

        # If we are busy (thinking or speaking) and we didn't ignore it, interrupt first
        if is_busy:
            log.info("Interrupting current action for new command: '%s'.", text)
            self.interrupt_processing()

        # Start a new query thread
        self.start_processing_thread(text)

    def start_processing_thread(self, text: str):
        self.interrupted = False
        self.processing_thread = threading.Thread(
            target=self.run_processing,
            args=(text,),
            daemon=True
        )
        self.processing_thread.start()

    def interrupt_processing(self):
        self.interrupted = True
        tts_manager.stop()
        self.set_state("idle")

    def trigger_double_clap_actions(self):
        log.info("Running double clap actions...")
        # 1. Play song
        spotify_uri = settings_manager.get("spotify_uri", "")
        if spotify_uri:
            tool_registry.execute(f'[TOOL: play_song("{spotify_uri}")]')
            
        # 2. Open Claude in Chrome
        open_claude = settings_manager.get("open_claude_in_chrome", False)
        if open_claude:
            tool_registry.execute('[TOOL: open_claude()]')
            
        # 3. Delay before listening (gives browser time to start)
        delay = settings_manager.get("jarvis_after_song_delay_s", 1.0)
        if delay > 0:
            time.sleep(delay)
            
        # 4. Speak welcome phrase
        user_name = db_manager.get_memory("user_name")
        welcome = f"Welcome back, {user_name}! I am listening." if user_name else "I am listening. How can I help you today?"
        tts_manager.speak(welcome)
        
        # 5. Enable voice recording once
        self.trigger_voice_record_once = True

    def parse_local_command(self, text: str) -> tuple[str | None, bool]:
        """
        Parse text for simple local commands and execute them directly via tool_registry.
        Returns (response_text, was_handled).
        """
        import re
        clean = text.lower().strip().rstrip(".?!")
        
        # 1. Stop / Cancel
        if clean in ("stop", "cancel", "shut up", "quiet", "stop jarvis", "hold on", "never mind"):
            return ("Stopped.", True)
            
        # 1a. Stop YouTube / Stop YT
        if clean in ("stop youtube", "stop yt", "close youtube", "close yt", "stop youtube music", "stop yt music"):
            res = tool_registry.execute('[TOOL: stop_youtube()]')
            return (res, True)
            
        # 1b. Conversational/Greeting commands
        if clean in ("hello", "hi", "hey", "greetings", "hi jarvis", "hello jarvis", "hey jarvis"):
            return ("Hello. How can I help you today?", True)
            
        if clean in ("how are you", "how are you doing", "how's it going"):
            return ("I am doing great, thank you! Ready to assist you.", True)
            
        if clean in ("who are you", "what is your name", "what are you"):
            return ("I am Jarvis, your desktop AI assistant.", True)

        if clean in ("thank you", "thanks", "thank you jarvis", "thanks jarvis"):
            return ("You are very welcome!", True)

        if clean in ("what can you do", "help", "what are your features"):
            return ("I can open YouTube, YouTube Music, and Spotify, play requested songs, take screenshots, lock your PC, add notes, and save calendar reminders. Just ask me!", True)

        if "time" in clean:
            import time
            return (f"The current time is {time.strftime('%I:%M %p')}.", True)
            
        if "date" in clean:
            import time
            return (f"Today is {time.strftime('%A, %B %d, %Y')}.", True)

        # 1c. Name introduction/updating commands
        name_match = re.search(r"\b(?:i'm|i\s+am|my\s+name\s+is|call\s+me)\s+([a-zA-Z\s]+)", clean)
        if name_match:
            raw_name = name_match.group(1).strip()
            words = raw_name.split()
            if 0 < len(words) <= 2:
                first_word = words[0]
                exclude = {"ready", "hungry", "sad", "happy", "tired", "fine", "good", "here", "there", "going", "doing", "playing", "eating", "listening", "thinking", "speaking", "stopped", "sorry", "sure", "ok", "okay"}
                if first_word not in exclude:
                    capitalized_name = raw_name.title()
                    db_manager.add_memory("user_name", capitalized_name)
                    return (f"Nice to meet you, {capitalized_name}! I have updated your name on the dashboard.", True)
            
        # 2. YouTube / YT Music / YT commands
        if "youtube" in clean or "yt" in clean:
            query = None
            for trigger in ("play ", "search "):
                if trigger in clean:
                    query = clean.split(trigger, 1)[1].strip()
                    for suffix in (" on youtube music", " on yt music", " on youtube", " on yt", " youtube music", " yt music", " youtube", " yt"):
                        if query.endswith(suffix):
                            query = query[:-len(suffix)].strip()
                    break
            
            if query:
                safe_query = query.replace('"', '\\"')
                if "music" in clean:
                    res = tool_registry.execute(f'[TOOL: open_youtube_music("{safe_query}")]')
                else:
                    res = tool_registry.execute(f'[TOOL: open_youtube("{safe_query}")]')
            else:
                if "music" in clean:
                    res = tool_registry.execute('[TOOL: open_youtube_music()]')
                else:
                    res = tool_registry.execute('[TOOL: open_youtube()]')
            return (res, True)

        # 3. Spotify commands
        if "spotify" in clean:
            query = None
            for trigger in ("play ", "search "):
                if trigger in clean:
                    query = clean.split(trigger, 1)[1].strip()
                    for suffix in (" on spotify", " spotify"):
                        if query.endswith(suffix):
                            query = query[:-len(suffix)].strip()
                    break
            if query:
                safe_query = query.replace('"', '\\"')
                res = tool_registry.execute(f'[TOOL: open_spotify("{safe_query}")]')
            else:
                res = tool_registry.execute('[TOOL: open_spotify()]')
            return (res, True)

        # 4. Note commands
        if "note" in clean or any(phrase in clean for phrase in ("what does the note say", "show me the note", "tell me about the note", "what's the note")):
            if clean in ("create note", "create a note", "add note", "add a note", "make note", "make a note", "write note", "write a note", "note down"):
                self.create_note_requested.emit()
                return ("Opening note creation dialog on the dashboard.", True)

            # Clear / Delete all notes command
            if clean in ("delete the note", "delete the notes", "delete notes", "delete all notes", "clear notes", "clear all notes"):
                try:
                    conn = db_manager.get_connection()
                    cursor = conn.cursor()
                    cursor.execute("DELETE FROM notes")
                    conn.commit()
                    conn.close()
                    return ("All notes have been deleted successfully.", True)
                except Exception as e:
                    log.error("Failed to clear notes: %s", e)
                    return ("Failed to delete notes.", True)

            # Delete specific note by title
            for trigger in ("delete note ", "delete the note "):
                if trigger in clean:
                    title = clean.split(trigger, 1)[1].strip()
                    if title in ("", "note", "notes", "all notes"):
                        pass
                    else:
                        note = db_manager.get_note_by_title(title)
                        if note:
                            db_manager.delete_note(note['id'])
                            return (f"Deleted note '{note['title']}'.", True)
                        else:
                            return (f"Could not find a note matching '{title}'.", True)

            content = None
            is_creation = False
            
            if "note down " in clean:
                content = clean.split("note down ", 1)[1].strip()
                is_creation = True
            elif "make a note " in clean or "make note " in clean:
                parts = clean.split("note ", 1)
                if len(parts) > 1:
                    content = parts[1].strip()
                    is_creation = True
            elif "add note " in clean or "add a note " in clean:
                parts = clean.split("note ", 1)
                if len(parts) > 1:
                    content = parts[1].strip()
                    is_creation = True
            elif "create note " in clean or "create a note " in clean:
                parts = clean.split("note ", 1)
                if len(parts) > 1:
                    content = parts[1].strip()
                    is_creation = True
            elif "save note " in clean or "save a note " in clean:
                parts = clean.split("note ", 1)
                if len(parts) > 1:
                    content = parts[1].strip()
                    is_creation = True
            elif "write note " in clean or "write a note " in clean:
                parts = clean.split("note ", 1)
                if len(parts) > 1:
                    content = parts[1].strip()
                    is_creation = True
            elif "open the note and make " in clean or "open note and make " in clean:
                parts = clean.split("make ", 1)
                if len(parts) > 1:
                    content = parts[1].strip()
                    is_creation = True
            
            if is_creation and content:
                # Remove joining words at the start of the content (including "with ")
                for prefix in ("to ", "about ", "that ", "with "):
                    if content.startswith(prefix):
                        content = content[len(prefix):].strip()
                words = content.split()
                title = " ".join(words[:3]).capitalize() if words else "Voice Note"
                safe_title = title.replace('"', '\\"')
                safe_content = content.replace('"', '\\"')
                res = tool_registry.execute(f'[TOOL: add_note("{safe_title}", "{safe_content}")]')
                return (res, True)
                
            # If they ask "read the note", "what is the note", "read my note", "tell me the note", etc.
            if clean in ("read the note", "what is the note", "read my note", "tell me the note", "what does the note say", "show me the note", "tell me about the note", "what's the note"):
                notes = db_manager.get_notes()
                if notes:
                    latest = notes[0]
                    return (f"Your note says: {latest['content']}.", True)
                else:
                    return ("You don't have any notes saved yet.", True)

            if any(phrase in clean for phrase in ("list notes", "show notes", "open notes", "my notes", "read notes")):
                res = tool_registry.execute('[TOOL: list_notes()]')
                return (res, True)
                
            for trigger in ("read note ", "open note ", "show note "):
                if trigger in clean:
                    title = clean.split(trigger, 1)[1].strip()
                    if title in ("", "note", "notes"):
                        res = tool_registry.execute('[TOOL: list_notes()]')
                    else:
                        safe_title = title.replace('"', '\\"')
                        res = tool_registry.execute(f'[TOOL: read_note("{safe_title}")]')
                    return (res, True)

        # 5. Calendar Reminder commands
        if "remind" in clean or "reminder" in clean:
            reminder_text = None
            for trigger in ("remind me to ", "remind me ", "reminder for ", "reminder "):
                if trigger in clean:
                    reminder_text = clean.split(trigger, 1)[1].strip()
                    break
            
            if reminder_text:
                when_text = ""
                time_match = re.search(r"\b(?:at|tomorrow|on|next)\b.*", reminder_text)
                if time_match:
                    when_text = time_match.group(0).strip()
                    reminder_text = reminder_text.replace(when_text, "").strip()
                    
                safe_title = reminder_text.replace('"', '\\"')
                safe_when = when_text.replace('"', '\\"')
                if safe_when:
                    res = tool_registry.execute(f'[TOOL: add_calendar_reminder("{safe_title}", "{safe_when}")]')
                else:
                    res = tool_registry.execute(f'[TOOL: add_calendar_reminder("{safe_title}")]')
                return (res, True)

        # 6. Task / Todo commands
        if "task" in clean or "todo" in clean:
            # Check for empty creation commands
            if clean in ("add task", "add a task", "create task", "create a todo", "add todo", "add a todo", "new task"):
                self.create_task_requested.emit()
                return ("Opening task creation dialog on the dashboard.", True)

            # Add task with description
            for trigger in ("add task ", "add a task ", "create task ", "create todo ", "add todo ", "add a todo "):
                if trigger in clean:
                    task = clean.split(trigger, 1)[1].strip()
                    db_manager.add_todo(task)
                    return (f"Added task: '{task}'.", True)

            # Complete / Finish task
            for trigger in ("complete task ", "complete todo ", "finish task ", "finish todo "):
                if trigger in clean:
                    task_name = clean.split(trigger, 1)[1].strip()
                    try:
                        conn = db_manager.get_connection()
                        cursor = conn.cursor()
                        cursor.execute("SELECT id, task FROM todos WHERE task LIKE ? AND status = 'pending' LIMIT 1", (f"%{task_name}%",))
                        row = cursor.fetchone()
                        if row:
                            cursor.execute("UPDATE todos SET status = 'completed' WHERE id = ?", (row['id'],))
                            conn.commit()
                            conn.close()
                            return (f"Marked task '{row['task']}' as completed.", True)
                        else:
                            conn.close()
                            return (f"Could not find a pending task matching '{task_name}'.", True)
                    except Exception as e:
                        log.error("Failed to complete task: %s", e)
                        return ("Failed to complete task.", True)

            # Delete specific task
            for trigger in ("delete task ", "delete todo "):
                if trigger in clean:
                    task_name = clean.split(trigger, 1)[1].strip()
                    try:
                        conn = db_manager.get_connection()
                        cursor = conn.cursor()
                        cursor.execute("SELECT id, task FROM todos WHERE task LIKE ? LIMIT 1", (f"%{task_name}%",))
                        row = cursor.fetchone()
                        if row:
                            cursor.execute("DELETE FROM todos WHERE id = ?", (row['id'],))
                            conn.commit()
                            conn.close()
                            return (f"Deleted task '{row['task']}'.", True)
                        else:
                            conn.close()
                            return (f"Could not find a task matching '{task_name}'.", True)
                    except Exception as e:
                        log.error("Failed to delete task: %s", e)
                        return ("Failed to delete task.", True)

            # Delete / Clear all tasks
            if clean in ("delete all tasks", "delete tasks", "clear tasks", "clear all tasks", "delete todos", "delete all todos", "clear todos", "clear all todos"):
                try:
                    conn = db_manager.get_connection()
                    cursor = conn.cursor()
                    cursor.execute("DELETE FROM todos")
                    conn.commit()
                    conn.close()
                    return ("All tasks have been deleted successfully.", True)
                except Exception as e:
                    log.error("Failed to clear tasks: %s", e)
                    return ("Failed to delete tasks.", True)

            # List/Show tasks
            if clean in ("list tasks", "show tasks", "my tasks", "what are my tasks", "list todos", "show todos", "my todos", "what are my todos"):
                res = tool_registry.execute('[TOOL: list_todos()]')
                return (res, True)

        # 7. Git Automation commands
        if "git" in clean or "commit" in clean or "push to github" in clean or "push to repo" in clean:
            if clean in ("git status", "check git status", "check repo status", "repository status"):
                res = tool_registry.execute('[TOOL: git_status()]')
                return (res, True)

            if "commit and push" in clean or "push code" in clean or "push to github" in clean or "push to repo" in clean or clean in ("git push", "push changes"):
                # First commit if there are pending changes, then push
                msg = "Update Jarvis repository"
                if "with message " in clean:
                    msg = clean.split("with message ", 1)[1].strip()
                commit_res = tool_registry.execute(f'[TOOL: git_commit("{msg}")]')
                push_res = tool_registry.execute('[TOOL: git_push("main")]')
                return (f"{commit_res}\n{push_res}", True)

            if "commit" in clean:
                msg = "Update Jarvis repository"
                if "with message " in clean or "message " in clean:
                    msg = clean.split("message ", 1)[1].strip()
                res = tool_registry.execute(f'[TOOL: git_commit("{msg}")]')
                return (res, True)

            if "git pull" in clean or "pull code" in clean:
                res = tool_registry.execute('[TOOL: git_pull("main")]')
                return (res, True)

        return (None, False)


    def run_processing(self, text: str):
        current_thread = threading.current_thread()
        try:
            self.set_state("thinking")
            
            # Save user message to database
            db_manager.add_history("user", text)
            
            if self.processing_thread is not current_thread or self.interrupted:
                return

            # Check if this is a simple local command first
            reply, was_handled = self.parse_local_command(text)
            tool_tag = None
            
            if not was_handled:
                # Query Ollama
                history = db_manager.get_history(limit=10)
                reply, tool_tag = ollama_client.query(text, history)
                
                if self.processing_thread is not current_thread or self.interrupted:
                    return

                # Save assistant message to database
                db_manager.add_history("assistant", reply)
                self.response_received.emit("Jarvis", reply)
            else:
                if self.processing_thread is not current_thread or self.interrupted:
                    return
                # For local commands, just display response
                self.response_received.emit("Jarvis", reply)
            
            self.set_state("speaking")
            
            if self.processing_thread is not current_thread or self.interrupted:
                return

            tts_manager.speak(reply)
            
            if self.processing_thread is not current_thread or self.interrupted:
                return

            # Execute tool call if returned from Ollama
            if tool_tag:
                self.response_received.emit("System", f"Running action: {tool_tag}...")
                result = tool_registry.execute(tool_tag)
                self.response_received.emit("System", result)
                
                # Speak short success feedback if appropriate
                if self.processing_thread is current_thread and not self.interrupted and "error" not in result.lower():
                    tts_manager.speak("Done.")
        except Exception as e:
            log.error("Error in processing thread: %s", e)
        finally:
            if self.processing_thread is current_thread and not self.interrupted:
                self.set_state("idle")


class JarvisApplication:
    def __init__(self):
        self.app = QApplication(sys.argv)
        self.app.setQuitOnLastWindowClosed(False)

        # Main window and Floating Widget
        self.main_window = MainWindow()
        self.floating_widget = FloatingAssistant()

        # Position floating widget at bottom right of primary screen
        screen_geo = self.app.primaryScreen().geometry()
        self.floating_widget.move(
            screen_geo.width() - 110,
            screen_geo.height() - 150
        )
        self.floating_widget.show()

        # Connect signals
        self.main_window.text_submitted.connect(self.submit_typed_command)
        self.floating_widget.clicked.connect(self.toggle_main_window)

        # Setup System Tray
        self.setup_system_tray()

        # Start background voice worker thread
        self.worker = VoiceWorker()
        self.worker.state_changed.connect(self.on_worker_state_changed)
        self.worker.response_received.connect(self.on_worker_response)
        self.worker.create_note_requested.connect(self.main_window.add_note_ui)
        self.worker.create_task_requested.connect(self.main_window.add_todo)
        self.worker.start()

        # Say startup greeting
        user_name = db_manager.get_memory("user_name")
        greeting = f"Jarvis online. Welcome back, {user_name}! How can I help you today?" if user_name else "Jarvis online. How can I help you today?"
        self.on_worker_response("Jarvis", greeting)
        threading.Thread(
            target=lambda: tts_manager.speak(greeting),
            daemon=True
        ).start()

    def setup_system_tray(self):
        self.tray_icon = QSystemTrayIcon(self.app)
        
        # Use simple custom styling or default tray icon
        # Create a tiny 16x16 circular color icon for tray
        from PySide6.QtGui import QPixmap, QColor, QPainter
        pixmap = QPixmap(16, 16)
        pixmap.fill(Qt.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setBrush(QColor(0, 229, 255)) # Cyan
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(2, 2, 12, 12)
        painter.end()
        
        self.tray_icon.setIcon(QIcon(pixmap))
        self.tray_icon.setToolTip("Jarvis - Desktop AI Assistant")

        # Tray Context Menu
        menu = QMenu()
        show_action = QAction("Open Dashboard", menu)
        show_action.triggered.connect(self.show_main_window)
        
        hide_action = QAction("Hide Dashboard", menu)
        hide_action.triggered.connect(self.hide_main_window)
        
        exit_action = QAction("Exit Jarvis", menu)
        exit_action.triggered.connect(self.exit_application)

        menu.addAction(show_action)
        menu.addAction(hide_action)
        menu.addSeparator()
        menu.addAction(exit_action)

        self.tray_icon.setContextMenu(menu)
        self.tray_icon.activated.connect(self.on_tray_activated)
        self.tray_icon.show()

    def on_tray_activated(self, reason):
        if reason == QSystemTrayIcon.Trigger: # Left click
            self.toggle_main_window()

    def toggle_main_window(self):
        if self.main_window.isVisible():
            self.main_window.hide()
        else:
            self.show_main_window()

    def show_main_window(self):
        self.main_window.show()
        self.main_window.raise_()
        self.main_window.activateWindow()

    def hide_main_window(self):
        self.main_window.hide()

    @Slot(str)
    def submit_typed_command(self, text: str):
        self.worker.submit_command(text)

    @Slot(str)
    def on_worker_state_changed(self, state: str):
        self.floating_widget.set_state(state)

    @Slot(str, str)
    def on_worker_response(self, sender: str, message: str):
        self.main_window.append_message(sender, message)
        self.main_window.refresh_user_label()
        self.main_window.refresh_memories()
        self.main_window.refresh_notes()
        self.main_window.refresh_todos()

    def exit_application(self):
        log.info("Exiting application...")
        self.worker.stop()
        self.worker.wait()
        plugin_manager.unload_all()
        self.app.quit()
        sys.exit(0)

    def run(self):
        return self.app.exec()

if __name__ == "__main__":
    import signal
    # Force default signal handler for SIGINT (Ctrl+C) to terminate the app instantly
    signal.signal(signal.SIGINT, signal.SIG_DFL)
    
    try:
        app_instance = JarvisApplication()
        sys.exit(app_instance.run())
    except KeyboardInterrupt:
        print("\nExiting Jarvis...")
        sys.exit(0)
