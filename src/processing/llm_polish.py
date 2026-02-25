"""
LLM-based text polishing via Ollama.

Sends raw transcription to a local LLM for high-quality cleanup:
filler removal, punctuation, self-correction handling, and natural flow.
Falls back gracefully if Ollama is unavailable.
"""
import logging
from typing import Optional

import requests

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = (
    "You are a transcription editor. Your job is to clean up raw voice dictation. "
    "Rules:\n"
    "1. Remove filler words (um, uh, like, you know, I mean, etc.)\n"
    "2. Fix punctuation and capitalization\n"
    "3. Handle self-corrections: 'meet at 4, no wait 3 pm' → 'meet at 3 pm'\n"
    "4. Format spoken lists as numbered or bulleted lists when appropriate\n"
    "5. Keep the meaning IDENTICAL — do not add, remove, or change content\n"
    "6. Return ONLY the cleaned text, no explanations or metadata"
)


def is_ollama_available(base_url: str = "http://localhost:11434", timeout: float = 1.0) -> bool:
    """Quick check whether the Ollama server is running."""
    try:
        resp = requests.get(f"{base_url}/api/tags", timeout=timeout)
        return resp.status_code == 200
    except requests.RequestException:
        return False


def polish_text(
    raw_text: str,
    ollama_model: str = "llama3.2:3b",
    ollama_url: str = "http://localhost:11434",
    context_app: str = "",
    timeout: float = 10.0,
) -> Optional[str]:
    """
    Polish raw transcription text using a local Ollama LLM.

    Returns the polished text, or None if Ollama is unavailable or fails.
    Callers should fall back to rule-based cleanup on None.
    """
    if not raw_text.strip():
        return raw_text

    context_hint = ""
    if context_app:
        context_hint = f"\nContext: This text will be inserted into {context_app}."

    prompt = (
        f"{context_hint}\n\nRaw dictation:\n{raw_text}\n\nCleaned text:"
    ).strip()

    try:
        response = requests.post(
            f"{ollama_url}/api/generate",
            json={
                "model": ollama_model,
                "system": _SYSTEM_PROMPT,
                "prompt": prompt,
                "stream": False,
                "options": {
                    "temperature": 0.1,  # Low temp for deterministic cleanup
                    "num_predict": 500,
                },
            },
            timeout=timeout,
        )
        response.raise_for_status()
        data = response.json()
        cleaned = data.get("response", "").strip()

        if not cleaned:
            logger.warning("Ollama returned empty response")
            return None

        logger.debug(f"LLM polish: {raw_text!r} → {cleaned!r}")
        return cleaned

    except requests.exceptions.ConnectionError:
        logger.info("Ollama not running — skipping LLM polish")
        return None
    except requests.exceptions.Timeout:
        logger.warning(f"Ollama request timed out after {timeout}s")
        return None
    except Exception:
        logger.exception("LLM polish failed unexpectedly")
        return None
