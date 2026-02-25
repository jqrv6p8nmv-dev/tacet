"""
Custom dictionary for user-defined word replacements.

Loaded from ~/.config/flowvoice/custom_dictionary.json.
Supports exact-match and case-insensitive replacements.
"""
import json
import logging
import os
import re
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

DEFAULT_DICT_PATH = Path("~/.config/flowvoice/custom_dictionary.json").expanduser()


class CustomDictionary:
    """Applies user-defined word/phrase substitutions to transcribed text."""

    def __init__(self, path: Optional[Path] = None):
        self.path = path or DEFAULT_DICT_PATH
        self._replacements: dict[str, str] = {}
        self.load()

    def load(self) -> None:
        """Load replacements from the JSON file. Silently skips if missing."""
        if not self.path.exists():
            logger.debug(f"Custom dictionary not found at {self.path} — skipping")
            return

        try:
            with open(self.path) as f:
                data = json.load(f)
            self._replacements = data.get("replacements", {})
            logger.info(f"Loaded {len(self._replacements)} custom dictionary entries")
        except (json.JSONDecodeError, OSError):
            logger.exception(f"Failed to load custom dictionary from {self.path}")

    def apply(self, text: str) -> str:
        """Apply all replacements to text (case-insensitive matching)."""
        if not self._replacements or not text:
            return text

        result = text
        # Sort by length descending so longer phrases are matched first
        for source, target in sorted(
            self._replacements.items(), key=lambda kv: len(kv[0]), reverse=True
        ):
            escaped = re.escape(source)
            result = re.sub(rf"\b{escaped}\b", target, result, flags=re.IGNORECASE)

        return result

    def add_entry(self, spoken: str, replacement: str) -> None:
        """Add a new entry and persist to disk."""
        self._replacements[spoken] = replacement
        self._save()

    def remove_entry(self, spoken: str) -> bool:
        """Remove an entry. Returns True if it existed."""
        if spoken in self._replacements:
            del self._replacements[spoken]
            self._save()
            return True
        return False

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.path, "w") as f:
            json.dump({"replacements": self._replacements}, f, indent=2)

    def __len__(self) -> int:
        return len(self._replacements)
