"""
Global hotkey listener using pynput.

Supports two modes:
  - Hold-to-record (default for Fn key): press starts recording, release stops it.
  - Toggle (for combo keys like Ctrl+Shift+Space): each press flips the state.

The Fn key on macOS is a bare modifier key and cannot be registered via
pynput's GlobalHotKeys. Instead we use a raw keyboard.Listener and check
for Key.fn on press/release events.
"""
import logging
import threading
from typing import Callable, Optional

from pynput import keyboard

logger = logging.getLogger(__name__)

DEFAULT_HOTKEY = "fn"

# pynput key name → Key enum lookup
_SPECIAL_KEY_NAMES = {
    "fn": getattr(keyboard.Key, "fn", None),
    "ctrl": keyboard.Key.ctrl,
    "shift": keyboard.Key.shift,
    "alt": keyboard.Key.alt,
    "cmd": keyboard.Key.cmd,
    "space": keyboard.Key.space,
    "tab": keyboard.Key.tab,
    "enter": keyboard.Key.enter,
    "esc": keyboard.Key.esc,
}


def _is_fn_config(hotkey_str: str) -> bool:
    return hotkey_str.strip().lower().lstrip("<").rstrip(">") == "fn"


class FnHoldListener:
    """
    Hold-to-record listener for the bare Fn key.

    Press Fn → calls `on_press`.
    Release Fn → calls `on_release`.

    Uses pynput's raw keyboard.Listener so it can see individual modifier
    key events that GlobalHotKeys ignores.
    """

    def __init__(
        self,
        on_press: Optional[Callable] = None,
        on_release: Optional[Callable] = None,
    ):
        self.on_press_cb = on_press
        self.on_release_cb = on_release
        self._listener: Optional[keyboard.Listener] = None
        self._running = False
        self._fn_key = getattr(keyboard.Key, "fn", None)

        if self._fn_key is None:
            logger.warning(
                "pynput does not expose Key.fn on this system. "
                "Fn key detection may not work — consider using a combo hotkey instead."
            )

    def start(self) -> None:
        if self._running:
            return

        def _on_press(key):
            if self._fn_key is not None and key == self._fn_key:
                logger.debug("Fn key pressed")
                if self.on_press_cb:
                    threading.Thread(target=self.on_press_cb, daemon=True).start()

        def _on_release(key):
            if self._fn_key is not None and key == self._fn_key:
                logger.debug("Fn key released")
                if self.on_release_cb:
                    threading.Thread(target=self.on_release_cb, daemon=True).start()

        self._listener = keyboard.Listener(on_press=_on_press, on_release=_on_release)
        self._listener.daemon = True
        self._listener.start()
        self._running = True
        logger.info("Fn hold-to-record listener started")

    def stop(self) -> None:
        if self._listener:
            self._listener.stop()
            self._listener = None
        self._running = False
        logger.info("Fn hold-to-record listener stopped")

    # Expose same interface as HotkeyListener for duck-typing
    @property
    def hotkey_str(self) -> str:
        return "<fn>"

    @property
    def is_running(self) -> bool:
        return self._running


class HotkeyListener:
    """
    Toggle-mode listener for keyboard combos (e.g. Ctrl+Shift+Space).

    Each press of the hotkey toggles recording on/off via `on_activate`.
    """

    def __init__(
        self,
        hotkey: str = "<ctrl>+<shift>+<space>",
        on_activate: Optional[Callable] = None,
    ):
        self._hotkey_str = _parse_hotkey(hotkey)
        self.on_activate = on_activate
        self._listener: Optional[keyboard.GlobalHotKeys] = None
        self._running = False

    @property
    def hotkey_str(self) -> str:
        return self._hotkey_str

    def start(self) -> None:
        if self._running:
            return

        def _on_hotkey():
            logger.debug(f"Hotkey pressed: {self._hotkey_str}")
            if self.on_activate:
                threading.Thread(target=self.on_activate, daemon=True).start()

        self._listener = keyboard.GlobalHotKeys({self._hotkey_str: _on_hotkey})
        self._listener.daemon = True
        self._listener.start()
        self._running = True
        logger.info(f"Toggle hotkey listener started: {self._hotkey_str}")

    def stop(self) -> None:
        if self._listener:
            self._listener.stop()
            self._listener = None
        self._running = False
        logger.info("Toggle hotkey listener stopped")

    def update_hotkey(self, new_hotkey: str, on_activate: Optional[Callable] = None) -> None:
        was_running = self._running
        self.stop()
        self._hotkey_str = _parse_hotkey(new_hotkey)
        if on_activate is not None:
            self.on_activate = on_activate
        if was_running:
            self.start()

    @property
    def is_running(self) -> bool:
        return self._running


def _parse_hotkey(hotkey_str: str) -> str:
    """
    Convert config-style hotkey strings to pynput HotKey format.

    "ctrl+shift+space" → "<ctrl>+<shift>+<space>"
    "<ctrl>+<shift>+<space>" → unchanged
    """
    if "<" in hotkey_str:
        return hotkey_str
    parts = [p.strip() for p in hotkey_str.split("+")]
    converted = []
    for part in parts:
        low = part.lower()
        if low in _SPECIAL_KEY_NAMES or len(part) > 1:
            converted.append(f"<{low}>")
        else:
            converted.append(part)
    return "+".join(converted)


def create_listener(
    hotkey: str,
    on_activate: Optional[Callable] = None,
    on_start: Optional[Callable] = None,
    on_stop: Optional[Callable] = None,
):
    """
    Factory: return the right listener type for the configured hotkey.

    - "fn"  → FnHoldListener (hold-to-record; uses on_start / on_stop)
    - anything else → HotkeyListener (toggle; uses on_activate)
    """
    if _is_fn_config(hotkey):
        logger.info("Using Fn hold-to-record mode")
        return FnHoldListener(on_press=on_start, on_release=on_stop)
    else:
        logger.info(f"Using toggle mode for hotkey: {hotkey}")
        return HotkeyListener(hotkey=hotkey, on_activate=on_activate)
