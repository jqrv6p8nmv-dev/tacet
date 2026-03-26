"""
Whisper transcription engine.

Supports mlx-whisper (primary, Apple Silicon optimized) with a fallback
to openai-whisper for non-Apple-Silicon environments.
"""
import logging
from typing import Optional

import numpy as np

logger = logging.getLogger(__name__)


class WhisperEngine:
    """
    Wraps mlx-whisper (preferred on Apple Silicon) or openai-whisper as
    a fallback. Lazy-loads the model on first use to keep startup fast.
    """

    def __init__(
        self,
        model: str = "mlx-community/whisper-small-mlx",
        language: str = "en",
        backend: str = "mlx-whisper",
    ):
        self.model = model
        self.language = language
        self.backend = backend
        self._loaded = False

    def _ensure_loaded(self) -> None:
        """Import the backend on first use (avoids slow startup)."""
        if self._loaded:
            return

        if self.backend == "mlx-whisper":
            try:
                import mlx_whisper  # noqa: F401 — just verify importability
                logger.info(f"mlx-whisper backend ready (model: {self.model})")
            except ImportError as _mlx_err:
                logger.warning(
                    "mlx-whisper not available — falling back to openai-whisper",
                    exc_info=True,
                )
                self.backend = "openai-whisper"

        if self.backend == "openai-whisper":
            try:
                import whisper  # noqa: F401
                logger.info("openai-whisper backend ready")
            except ImportError as e:
                raise RuntimeError(
                    "No Whisper backend available. "
                    "Install mlx-whisper (Apple Silicon) or openai-whisper."
                ) from e

        self._loaded = True

    def warm_up(self) -> None:
        """Pre-load model weights by running a silent transcription at startup."""
        try:
            self.transcribe(np.zeros(1600, dtype=np.float32))  # 0.1s of silence
            logger.info("Whisper model warm-up complete")
        except Exception:
            logger.debug("Whisper warm-up failed (non-fatal)", exc_info=True)

    def transcribe(self, audio: np.ndarray) -> str:
        """
        Transcribe a float32 mono audio array at 16kHz.

        Returns the transcribed text string (stripped of leading/trailing
        whitespace). Returns an empty string on failure.
        """
        self._ensure_loaded()

        if audio is None or len(audio) == 0:
            return ""

        try:
            if self.backend == "mlx-whisper":
                return self._transcribe_mlx(audio)
            else:
                return self._transcribe_openai(audio)
        except Exception:
            logger.exception("Transcription failed")
            return ""

    def _transcribe_mlx(self, audio: np.ndarray) -> str:
        import mlx_whisper

        result = mlx_whisper.transcribe(
            audio,
            path_or_hf_repo=self.model,
            language=self.language if self.language != "auto" else None,
            verbose=False,
        )
        text = result.get("text", "").strip()
        logger.debug(f"MLX transcription: {text!r}")
        return text

    def _transcribe_openai(self, audio: np.ndarray) -> str:
        import whisper

        # openai-whisper loads by size name (tiny/base/small/medium/large)
        # Map HuggingFace repo names to size names for compatibility
        size_map = {
            "mlx-community/whisper-tiny-mlx": "tiny",
            "mlx-community/whisper-base-mlx": "base",
            "mlx-community/whisper-small-mlx": "small",
            "mlx-community/whisper-medium-mlx": "medium",
            "mlx-community/whisper-large-mlx": "large",
        }
        size = size_map.get(self.model, "small")

        model = whisper.load_model(size)
        result = model.transcribe(
            audio,
            language=self.language if self.language != "auto" else None,
            fp16=False,
        )
        text = result.get("text", "").strip()
        logger.debug(f"OpenAI-whisper transcription: {text!r}")
        return text
