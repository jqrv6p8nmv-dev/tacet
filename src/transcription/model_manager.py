"""
Model management utilities — list available models, validate selections,
and report download status.
"""
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# Ordered from fastest/smallest to most accurate/largest
AVAILABLE_MODELS = [
    {
        "id": "mlx-community/whisper-tiny-mlx",
        "size": "tiny",
        "display": "Tiny (~75MB) — fastest, lower accuracy",
        "vram_mb": 75,
    },
    {
        "id": "mlx-community/whisper-base-mlx",
        "size": "base",
        "display": "Base (~150MB) — fast, decent accuracy",
        "vram_mb": 150,
    },
    {
        "id": "mlx-community/whisper-small-mlx",
        "size": "small",
        "display": "Small (~500MB) — recommended balance (default)",
        "vram_mb": 500,
    },
    {
        "id": "mlx-community/whisper-medium-mlx",
        "size": "medium",
        "display": "Medium (~1.5GB) — higher accuracy, slower",
        "vram_mb": 1500,
    },
    {
        "id": "mlx-community/whisper-large-v3-mlx",
        "size": "large",
        "display": "Large v3 (~3GB) — best accuracy, slowest",
        "vram_mb": 3000,
    },
]

DEFAULT_MODEL = "mlx-community/whisper-small-mlx"


def get_model_info(model_id: str) -> Optional[dict]:
    """Return metadata for a given model ID, or None if not found."""
    for m in AVAILABLE_MODELS:
        if m["id"] == model_id:
            return m
    return None


def is_valid_model(model_id: str) -> bool:
    return any(m["id"] == model_id for m in AVAILABLE_MODELS)


def list_models() -> list[dict]:
    return list(AVAILABLE_MODELS)


def check_mlx_available() -> bool:
    """Return True if mlx-whisper is importable."""
    try:
        import mlx_whisper  # noqa: F401
        return True
    except ImportError:
        return False


def check_openai_whisper_available() -> bool:
    """Return True if openai-whisper is importable."""
    try:
        import whisper  # noqa: F401
        return True
    except ImportError:
        return False


def get_best_backend() -> str:
    """Return the best available backend for the current machine."""
    if check_mlx_available():
        return "mlx-whisper"
    if check_openai_whisper_available():
        return "openai-whisper"
    raise RuntimeError(
        "No Whisper backend found. "
        "Run: pip install mlx-whisper  (Apple Silicon) or pip install openai-whisper"
    )
