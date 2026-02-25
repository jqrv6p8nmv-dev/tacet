"""
Global hotkey listener using pynput.

Registers system-wide hotkeys that fire even when the app is not focused.
Default hotkey: Ctrl+Shift+Space (toggle recording on/off).
"""
import logging
import threading
from typing import Callable, Optional, Set

from pynput import keyboard

logger = logging.getLogger(__name__)

# Default hotkey combo
DEFAULT_HOTKEY = "<ctrl>+<shift>+<space>"


def _parse_hotkey(hotkey_str: str) -> str:
    """
    Convert config-style hotkey strings to pynput HotKey format.

    Examples:
      "ctrl+shift+space" → "<ctrl>+<shift>+<space>"
      "<ctrl>+<shift>+<space>" → unchanged
    """
    if "<" in hotkey_str:
        return hotkey_str  # Already in pynput format

    parts = [p.strip() for p in hotkey_str.split("+")]
    converted = []
    for part in parts:
        low = part.lower()
        if low in ("ctrl", "control", "cmd", "command", "alt", "option",
                   "shift", "space", "tab", "enter", "esc", "fn"):
            converted.append(f"<{low}>")
        elif len(part) == 1:
            converted.append(part)
        else:
            converted.append(f"<{low}>")
    return "+".join(converted)


class HotkeyListener:
    """
    Listens for a global toggle hotkey (default: Ctrl+Shift+Space).

    Calls `on_activate` each time the hotkey is pressed.
    Runs on a background daemon thread.
    """

    def __init__(
        self,
        hotkey: str = DEFAULT_HOTKEY,
        on_activate: Optional[Callable] = None,
    ):
        self.hotkey_str = _parse_hotkey(hotkey)
        self.on_activate = on_activate
        self._listener: Optional[keyboard.GlobalHotKeys] = None
        self._running = False

    def start(self) -> None:
        """Start listening for the hotkey in a background thread."""
        if self._running:
            return

        def _on_hotkey():
            logger.debug(f"Hotkey pressed: {self.hotkey_str}")
            if self.on_activate:
                # Fire callback on a separate thread to avoid blocking the listener
                t = threading.Thread(target=self.on_activate, daemon=True)
                t.start()

        self._listener = keyboard.GlobalHotKeys({self.hotkey_str: _on_hotkey})
        self._listener.daemon = True
        self._listener.start()
        self._running = True
        logger.info(f"Hotkey listener started: {self.hotkey_str}")

    def stop(self) -> None:
        """Stop the hotkey listener."""
        if self._listener:
            self._listener.stop()
            self._listener = None
        self._running = False
        logger.info("Hotkey listener stopped")

    def update_hotkey(self, new_hotkey: str, on_activate: Optional[Callable] = None) -> None:
        """Replace the active hotkey combo (restarts the listener)."""
        was_running = self._running
        self.stop()
        self.hotkey_str = _parse_hotkey(new_hotkey)
        if on_activate is not None:
            self.on_activate = on_activate
        if was_running:
            self.start()

    @property
    def is_running(self) -> bool:
        return self._running
