"""
Microphone capture using sounddevice.

Records at 16kHz mono (Whisper's expected format) and uses a ring buffer
approach with silence detection for auto-stop.
"""
import logging
import threading
import time
from collections import deque
from typing import Callable, Optional

import numpy as np
import sounddevice as sd

logger = logging.getLogger(__name__)

SAMPLE_RATE = 16000
CHANNELS = 1
DTYPE = np.float32
CHUNK_SIZE = 1024  # samples per callback chunk


class AudioCapture:
    """Records audio from the default microphone with silence-based auto-stop."""

    def __init__(
        self,
        sample_rate: int = SAMPLE_RATE,
        silence_threshold: float = 0.01,
        silence_duration: float = 1.5,
        max_duration: float = 60.0,
        on_auto_stop: Optional[Callable] = None,
    ):
        self.sample_rate = sample_rate
        self.silence_threshold = silence_threshold
        self.silence_duration = silence_duration
        self.max_duration = max_duration
        self.on_auto_stop = on_auto_stop

        self._recording = False
        self._audio_chunks: list[np.ndarray] = []
        self._lock = threading.Lock()
        self._stream: Optional[sd.InputStream] = None
        self._silence_samples = 0
        self._start_time: float = 0.0

        # Pre-fill ring buffer to detect initial silence
        self._silence_ring: deque = deque(
            maxlen=int(sample_rate * silence_duration / CHUNK_SIZE) + 1
        )

    def start(self) -> None:
        """Begin recording from the default microphone."""
        if self._recording:
            logger.warning("AudioCapture.start() called while already recording")
            return

        self._recording = True
        self._audio_chunks = []
        self._silence_ring.clear()
        self._silence_samples = 0
        self._start_time = time.time()

        self._stream = sd.InputStream(
            samplerate=self.sample_rate,
            channels=CHANNELS,
            dtype=DTYPE,
            blocksize=CHUNK_SIZE,
            callback=self._audio_callback,
        )
        self._stream.start()
        logger.info("Recording started")

    def stop(self) -> Optional[np.ndarray]:
        """
        Stop recording and return the captured audio as a float32 numpy array.
        Returns None if no audio was captured.
        """
        if not self._recording:
            return None

        self._recording = False
        if self._stream:
            self._stream.stop()
            self._stream.close()
            self._stream = None

        with self._lock:
            chunks = list(self._audio_chunks)

        if not chunks:
            logger.warning("No audio captured")
            return None

        audio = np.concatenate(chunks, axis=0).flatten()
        duration = len(audio) / self.sample_rate
        logger.info(f"Recording stopped — {duration:.1f}s of audio captured")
        return audio

    def is_recording(self) -> bool:
        return self._recording

    def _audio_callback(
        self,
        indata: np.ndarray,
        frames: int,
        time_info,
        status: sd.CallbackFlags,
    ) -> None:
        if status:
            logger.debug(f"Audio stream status: {status}")

        if not self._recording:
            return

        chunk = indata.copy()

        with self._lock:
            self._audio_chunks.append(chunk)

        # Silence detection: RMS energy of chunk
        rms = float(np.sqrt(np.mean(chunk**2)))
        self._silence_ring.append(rms)

        elapsed = time.time() - self._start_time

        # Auto-stop on max duration
        if elapsed >= self.max_duration:
            logger.info(f"Max recording duration ({self.max_duration}s) reached")
            self._trigger_auto_stop()
            return

        # Auto-stop on sustained silence (only after at least 1s of speech)
        if elapsed > 1.0 and len(self._silence_ring) == self._silence_ring.maxlen:
            if all(r < self.silence_threshold for r in self._silence_ring):
                logger.info("Silence detected — auto-stopping recording")
                self._trigger_auto_stop()

    def _trigger_auto_stop(self) -> None:
        """Fire auto-stop on a background thread to avoid blocking the audio callback."""
        self._recording = False
        if self.on_auto_stop:
            t = threading.Thread(target=self.on_auto_stop, daemon=True)
            t.start()
