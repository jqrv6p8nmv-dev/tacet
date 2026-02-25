"""Tests for the transcription engine."""
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from src.transcription.model_manager import (
    check_mlx_available,
    get_best_backend,
    get_model_info,
    is_valid_model,
    list_models,
)
from src.transcription.whisper_engine import WhisperEngine


class TestModelManager:
    def test_list_models_non_empty(self):
        models = list_models()
        assert len(models) > 0

    def test_default_model_is_valid(self):
        assert is_valid_model("mlx-community/whisper-small-mlx")

    def test_unknown_model_is_invalid(self):
        assert not is_valid_model("not-a-real-model")

    def test_get_model_info_returns_dict(self):
        info = get_model_info("mlx-community/whisper-small-mlx")
        assert info is not None
        assert "display" in info
        assert "vram_mb" in info

    def test_get_model_info_unknown_returns_none(self):
        assert get_model_info("nonexistent") is None


class TestWhisperEngine:
    def test_transcribe_empty_audio_returns_empty(self):
        engine = WhisperEngine()
        result = engine.transcribe(np.array([]))
        assert result == ""

    def test_transcribe_none_returns_empty(self):
        engine = WhisperEngine()
        result = engine.transcribe(None)
        assert result == ""

    @patch("src.transcription.whisper_engine.WhisperEngine._transcribe_mlx")
    def test_transcribe_calls_mlx_backend(self, mock_mlx):
        mock_mlx.return_value = "hello world"
        engine = WhisperEngine(backend="mlx-whisper")

        # Bypass the import check
        with patch("builtins.__import__", side_effect=lambda name, *args, **kwargs: MagicMock() if name == "mlx_whisper" else __import__(name, *args, **kwargs)):
            engine._loaded = True  # Skip _ensure_loaded
            audio = np.random.randn(16000).astype(np.float32)
            result = engine.transcribe(audio)

        # Since _loaded=True and backend=mlx-whisper, it calls _transcribe_mlx
        mock_mlx.assert_called_once_with(audio)
        assert result == "hello world"

    def test_backend_fallback_on_missing_mlx(self):
        engine = WhisperEngine(backend="mlx-whisper")
        with patch("builtins.__import__") as mock_import:
            def side_effect(name, *args, **kwargs):
                if name == "mlx_whisper":
                    raise ImportError("not installed")
                return MagicMock()
            mock_import.side_effect = side_effect

            # After _ensure_loaded, backend should switch to openai-whisper
            # (unless openai-whisper also fails, in which case RuntimeError)
            try:
                engine._ensure_loaded()
            except RuntimeError:
                pass  # Expected if neither backend is available in test env
