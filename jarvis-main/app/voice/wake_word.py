import numpy as np
import sounddevice as sd
from app.utils.logger import log

class WakeWordDetector:
    def __init__(self, wake_word="hey jarvis"):
        self.wake_word = wake_word.lower()
        self.oww_model = None
        self._init_openwakeword()

    def _init_openwakeword(self):
        """Try to initialize openwakeword if installed."""
        try:
            import openwakeword
            from openwakeword.model import Model
            
            # Load default models or custom model
            # openwakeword has default models for 'hey_jarvis' or 'alexa'
            self.oww_model = Model(wakeword_models=["hey_jarvis"])
            log.info("openWakeWord model 'hey_jarvis' loaded successfully.")
        except Exception as e:
            log.warning("openWakeWord not available or failed to load: %s. Using Speech-based wake word fallback.", e)

    def listen_and_detect(self, audio_data: np.ndarray, sample_rate: int) -> bool:
        """
        Process a chunk of audio to detect the wake word.
        For openWakeWord: expects 16kHz, 16-bit mono PCM.
        """
        if self.oww_model is not None:
            try:
                # Convert float32 or int16 array to int16 expected by openwakeword
                if audio_data.dtype != np.int16:
                    audio_data_int16 = (audio_data * 32767).astype(np.int16)
                else:
                    audio_data_int16 = audio_data

                # openwakeword expects chunks of 1280 samples at 16000Hz
                # We feed the model
                prediction = self.oww_model.predict(audio_data_int16)
                for model_name, score in prediction.items():
                    if score > 0.5: # Threshold of 0.5
                        log.info("Wake word '%s' detected by openWakeWord! (Score: %.2f)", model_name, score)
                        return True
            except Exception as e:
                log.error("Error during openWakeWord inference: %s", e)
        
        return False
