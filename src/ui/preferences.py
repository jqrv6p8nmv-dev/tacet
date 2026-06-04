"""
Preferences window (Phase 2 placeholder).

In Phase 1, settings are managed via the config JSON file directly.
This module provides the hooks for a future native preferences UI.
"""
import logging

logger = logging.getLogger(__name__)


def show_preferences(config: dict, on_save=None) -> None:
    """
    Show a preferences dialog (stub — Phase 2 implementation).

    Currently opens the config file in the default text editor as a
    temporary workaround.
    """
    import subprocess
    from pathlib import Path

    config_path = Path("~/.config/tacet/config.json").expanduser()
    if config_path.exists():
        subprocess.run(["open", str(config_path)])
        logger.info(f"Opened config file: {config_path}")
    else:
        logger.warning(f"Config file not found: {config_path}")
