import numpy as np
from app.utils.logger import log

class WakeWordDetector:
    def __init__(self, wake_word="hey jarvis"):
        self.wake_word = wake_word.lower()
        self.oww_model = None
        self._init_openwakeword()

    def _init_openwakeword(self):
        """Try to initialize openwakeword if installed."""
        try:
            import openwakeword  # type: ignore
            from openwakeword.model import Model  # type: ignore
            
            # Load default models or custom model
            self.oww_model = Model(wakeword_models=["hey_jarvis"])
            log.info("openWakeWord model 'hey_jarvis' loaded successfully.")
        except Exception as e:
            log.info("openWakeWord module not installed. Operating with intelligent Speech/Text wake-word fallback (%s).", e)

    def listen_and_detect(self, audio_data: np.ndarray, sample_rate: int) -> bool:
        """
        Process a chunk of audio to detect the wake word via openWakeWord model.
        """
        if self.oww_model is not None:
            try:
                if audio_data.dtype != np.int16:
                    audio_data_int16 = (audio_data * 32767).astype(np.int16)
                else:
                    audio_data_int16 = audio_data

                prediction = self.oww_model.predict(audio_data_int16)
                for model_name, score in prediction.items():
                    if score > 0.5:
                        log.info("Wake word '%s' detected by openWakeWord! (Score: %.2f)", model_name, score)
                        return True
            except Exception as e:
                log.error("Error during openWakeWord inference: %s", e)
        
        return False

    def contains_wake_word(self, text: str) -> bool:
        """Check if transcribed text contains the wake word or variation."""
        if not text:
            return False
        clean = text.lower().strip()
        wake_words = ["jarvis", "hey jarvis", "hi jarvis", "hello jarvis", "ok jarvis", "okay jarvis"]
        return any(w in clean for w in wake_words)

    def strip_wake_word(self, text: str) -> str:
        """Cleanly strip wake word prefixes from user query."""
        if not text:
            return ""
        clean = text.strip()
        lower = clean.lower()
        wake_words = ["hey jarvis", "hello jarvis", "hi jarvis", "ok jarvis", "okay jarvis", "jarvis"]
        for w in wake_words:
            if lower.startswith(w):
                remainder = clean[len(w):].strip().lstrip(",.?! ")
                return remainder if remainder else clean
        return clean
