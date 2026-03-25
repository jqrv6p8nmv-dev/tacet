"""
Configuration management for WhisperMe.

Merges default config with user overrides stored at
~/.config/whisperme/config.json.
"""
import json
import logging
import os
import sys
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

CONFIG_DIR = Path("~/.config/whisperme").expanduser()
USER_CONFIG_PATH = CONFIG_DIR / "config.json"

# When running as a py2app bundle, __file__ points inside a zip archive and
# cannot be used for file I/O.  py2app sets the RESOURCEPATH env var to the
# real Contents/Resources/ directory, which is where DATA_FILES are placed.
if getattr(sys, "frozen", False):
    _resource_dir = Path(os.environ.get("RESOURCEPATH", ""))
    DEFAULT_CONFIG_PATH = _resource_dir / "config" / "default_config.json"
else:
    DEFAULT_CONFIG_PATH = Path(__file__).parent.parent / "config" / "default_config.json"


def _deep_merge(base: dict, override: dict) -> dict:
    """Recursively merge `override` into `base` (non-destructive)."""
    result = dict(base)
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def load_config() -> dict:
    """
    Load configuration: start with defaults, merge user overrides on top.
    """
    config: dict = {}

    if DEFAULT_CONFIG_PATH.exists():
        try:
            with open(DEFAULT_CONFIG_PATH) as f:
                config = json.load(f)
        except (json.JSONDecodeError, OSError):
            logger.warning(f"Failed to load default config from {DEFAULT_CONFIG_PATH}")
    else:
        logger.warning(f"Default config not found at {DEFAULT_CONFIG_PATH}")

    if USER_CONFIG_PATH.exists():
        try:
            with open(USER_CONFIG_PATH) as f:
                user_config = json.load(f)
            config = _deep_merge(config, user_config)
            logger.debug(f"Loaded user config from {USER_CONFIG_PATH}")
        except (json.JSONDecodeError, OSError):
            logger.warning(f"Failed to load user config from {USER_CONFIG_PATH}")

    return config


def save_config(config: dict) -> None:
    """Persist the current config to the user config file."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with open(USER_CONFIG_PATH, "w") as f:
        json.dump(config, f, indent=2)
    logger.debug(f"Config saved to {USER_CONFIG_PATH}")


def get(config: dict, *keys: str, default: Any = None) -> Any:
    """Safely get a nested config value."""
    node = config
    for key in keys:
        if not isinstance(node, dict):
            return default
        node = node.get(key, default)
        if node is default:
            return default
    return node
