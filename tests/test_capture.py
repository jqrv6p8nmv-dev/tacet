"""Tests for audio capture module."""
import time
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from src.audio.capture import AudioCapture
from src.audio.vad import has_speech, trim_silence


class TestAudioCapture:
    def test_not_recording_by_default(self):
        cap = AudioCapture()
        assert not cap.is_recording()

    def test_stop_when_not_recording_returns_none(self):
        cap = AudioCapture()
        result = cap.stop()
        assert result is None

    @patch("sounddevice.InputStream")
    def test_start_sets_recording_flag(self, mock_stream_cls):
        mock_stream = MagicMock()
        mock_stream_cls.return_value = mock_stream
        cap = AudioCapture()
        cap.start()
        assert cap.is_recording()
        cap._recording = False  # Clean up without real audio

    @patch("sounddevice.InputStream")
    def test_stop_returns_audio_when_chunks_present(self, mock_stream_cls):
        mock_stream = MagicMock()
        mock_stream_cls.return_value = mock_stream
        cap = AudioCapture()
        cap.start()

        # Inject fake audio chunk
        fake_chunk = np.random.randn(1024, 1).astype(np.float32)
        cap._audio_chunks.append(fake_chunk)

        audio = cap.stop()
        assert audio is not None
        assert isinstance(audio, np.ndarray)
        assert audio.dtype == np.float32

    def test_double_start_does_not_crash(self):
        cap = AudioCapture()
        with patch("sounddevice.InputStream") as mock_cls:
            mock_cls.return_value = MagicMock()
            cap.start()
            cap.start()  # Should no-op
            assert cap.is_recording()
            cap._recording = False

    def test_auto_stop_callback_is_called(self):
        callback = MagicMock()
        cap = AudioCapture(
            silence_threshold=1.0,  # Everything is "silence"
            silence_duration=0.001,
            on_auto_stop=callback,
        )
        # Simulate silent audio filling the ring buffer
        with patch("sounddevice.InputStream") as mock_cls:
            mock_cls.return_value = MagicMock()
            cap.start()
            cap._start_time = time.time() - 5  # Pretend 5s have passed

            # Feed silent chunks to fill ring buffer
            silent_chunk = np.zeros((1024, 1), dtype=np.float32)
            for _ in range(cap._silence_ring.maxlen + 1):
                cap._audio_callback(silent_chunk, 1024, None, 0)

            # Give the auto-stop thread a moment to fire
            time.sleep(0.1)
            callback.assert_called_once()


class TestVAD:
    def test_empty_audio_returns_false(self):
        assert not has_speech(np.array([]))
        assert not has_speech(None)

    def test_silent_audio_returns_false(self):
        silent = np.zeros(16000, dtype=np.float32)
        assert not has_speech(silent)

    def test_loud_audio_returns_true(self):
        loud = np.random.randn(16000).astype(np.float32) * 0.5
        assert has_speech(loud)

    def test_trim_silence_preserves_speech(self):
        # Silent start, speech in middle, silent end
        audio = np.zeros(32000, dtype=np.float32)
        audio[8000:24000] = np.random.randn(16000).astype(np.float32) * 0.5
        trimmed = trim_silence(audio)
        # Trimmed should be shorter than original
        assert len(trimmed) < len(audio)

    def test_trim_silence_all_silent_returns_original(self):
        silent = np.zeros(16000, dtype=np.float32)
        result = trim_silence(silent)
        assert len(result) == len(silent)
