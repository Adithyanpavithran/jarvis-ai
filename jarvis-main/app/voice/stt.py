import io
import wave
import numpy as np
import speech_recognition as sr
from app.utils.logger import log
from app.config.settings import settings_manager

class SpeechToTextManager:
    def __init__(self):
        self.faster_model = None
        self.standard_whisper = None
        self.recognizer = sr.Recognizer()
        
    def _init_standard_whisper(self):
        """Lazy load standard OpenAI whisper."""
        if self.standard_whisper is not None:
            return True
        try:
            import whisper
            model_size = settings_manager.get("whisper_model", "tiny.en")
            log.info("Loading standard whisper model '%s'...", model_size)
            self.standard_whisper = whisper.load_model(model_size)
            log.info("Standard whisper model loaded successfully.")
            return True
        except Exception as e:
            log.warning("Failed to load standard whisper: %s.", e)
            return False

    def _init_faster_whisper(self):
        """Lazy load faster-whisper model."""
        if self.faster_model is not None:
            return True
        try:
            from faster_whisper import WhisperModel  # type: ignore
            model_size = settings_manager.get("whisper_model", "tiny.en")
            log.info("Loading faster-whisper model '%s'...", model_size)
            self.faster_model = WhisperModel(model_size, device="cpu", compute_type="int8")
            log.info("faster-whisper model loaded successfully.")
            return True
        except Exception as e:
            log.warning("Failed to load faster-whisper: %s.", e)
            return False

    def transcribe(self, audio_data: sr.AudioData) -> str | None:
        """Transcribe AudioData using available backends (Whisper first, then Google API)."""
        backend = settings_manager.get("stt_backend", "whisper")

        # 1. Try standard OpenAI whisper first if backend is whisper or as high-quality local STT
        if backend == "whisper" or self.standard_whisper is not None:
            if self._init_standard_whisper():
                try:
                    wav_bytes = audio_data.get_wav_data(convert_rate=16000)
                    with wave.open(io.BytesIO(wav_bytes), "rb") as wf:
                        frames = wf.readframes(wf.getnframes())
                        pcm = np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0
                    
                    result = self.standard_whisper.transcribe(pcm, fp16=False)
                    text = (result.get("text") or "").strip()
                    if text:
                        log.info("STT (whisper): %s", text)
                        return text
                except Exception as e:
                    log.error("Standard whisper transcription failed: %s", e)

        # 2. Try faster-whisper
        if self._init_faster_whisper():
            try:
                wav_bytes = audio_data.get_wav_data(convert_rate=16000)
                with wave.open(io.BytesIO(wav_bytes), "rb") as wf:
                    frames = wf.readframes(wf.getnframes())
                    pcm = np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0
                
                segments, info = self.faster_model.transcribe(pcm, beam_size=5)
                text = "".join([segment.text for segment in segments]).strip()
                if text:
                    log.info("STT (faster-whisper): %s", text)
                    return text
            except Exception as e:
                log.error("faster-whisper transcription failed: %s", e)

        # 3. Fallback: Google Speech Recognition (free online API)
        try:
            log.info("Transcribing via Google Speech Recognition API...")
            text = self.recognizer.recognize_google(audio_data)
            if text:
                log.info("STT (Google API): %s", text)
                return text
        except sr.UnknownValueError:
            log.info("Google Speech Recognition could not understand audio.")
        except sr.RequestError as e:
            log.error("Google Speech Recognition request failed: %s", e)

        return None

stt_manager = SpeechToTextManager()
