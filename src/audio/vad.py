"""
Simple energy-based Voice Activity Detection (VAD).

This is a lightweight pre-filter to check whether an audio buffer
actually contains speech before sending it to Whisper.
"""
import logging

import numpy as np

logger = logging.getLogger(__name__)


def has_speech(
    audio: np.ndarray,
    sample_rate: int = 16000,
    energy_threshold: float = 0.005,
    min_speech_ratio: float = 0.1,
) -> bool:
    """
    Return True if the audio buffer likely contains speech.

    Uses a simple RMS energy heuristic: at least `min_speech_ratio` of
    25ms frames must exceed `energy_threshold`.

    Args:
        audio: float32 mono audio array
        sample_rate: samples per second
        energy_threshold: minimum RMS energy for a frame to count as speech
        min_speech_ratio: fraction of frames that must be above threshold
    """
    if audio is None or len(audio) == 0:
        return False

    frame_length = int(sample_rate * 0.025)  # 25ms frames
    if len(audio) < frame_length:
        return False

    # Reshape into frames (drop last partial frame)
    n_frames = len(audio) // frame_length
    frames = audio[: n_frames * frame_length].reshape(n_frames, frame_length)
    rms_per_frame = np.sqrt(np.mean(frames**2, axis=1))

    speech_frames = np.sum(rms_per_frame > energy_threshold)
    ratio = speech_frames / n_frames

    logger.debug(
        f"VAD: {speech_frames}/{n_frames} frames above threshold "
        f"({ratio:.1%}), min required {min_speech_ratio:.1%}"
    )
    return ratio >= min_speech_ratio


def trim_silence(
    audio: np.ndarray,
    sample_rate: int = 16000,
    energy_threshold: float = 0.005,
    pad_ms: int = 100,
) -> np.ndarray:
    """
    Trim leading and trailing silence from audio.

    Keeps `pad_ms` of silence as padding around speech to avoid clipping.
    """
    if audio is None or len(audio) == 0:
        return audio

    frame_length = int(sample_rate * 0.025)
    n_frames = len(audio) // frame_length
    if n_frames == 0:
        return audio

    frames = audio[: n_frames * frame_length].reshape(n_frames, frame_length)
    rms_per_frame = np.sqrt(np.mean(frames**2, axis=1))
    speech_mask = rms_per_frame > energy_threshold

    speech_indices = np.where(speech_mask)[0]
    if len(speech_indices) == 0:
        return audio  # No speech found — return as-is

    pad_frames = max(1, pad_ms * sample_rate // (frame_length * 1000))
    start_frame = max(0, speech_indices[0] - pad_frames)
    end_frame = min(n_frames, speech_indices[-1] + pad_frames + 1)

    return audio[start_frame * frame_length : end_frame * frame_length]
