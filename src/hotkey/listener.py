"""
Global hotkey listener.

HotkeyListener uses AppKit.NSEvent.addGlobalMonitorForEventsMatchingMask_handler_
(native macOS API) to avoid the pynput/ScriptMonitor crash on Ventura/Sonoma.
FnHoldListener keeps pynput for Fn-key detection (there is no NSEvent keycode for Fn).
"""
import logging
import threading
from typing import Callable, Optional

logger = logging.getLogger(__name__)

# ── Native macOS key constants ────────────────────────────────────────────────

_NSKeyDownMask = 1 << 10  # NSEventMaskKeyDown
_MOD_MASK = 0xFFFF0000    # device-independent modifier flags

_KEYCODE_MAP: dict[str, int] = {
    "space": 49, "return": 36, "enter": 36, "tab": 48,
    "esc": 53, "escape": 53, "delete": 51,
    "f1": 122, "f2": 120, "f3": 99, "f4": 118, "f5": 96,
    "f6": 97, "f7": 98, "f8": 100, "f9": 101, "f10": 109,
    "a": 0,  "b": 11, "c": 8,  "d": 2,  "e": 14, "f": 3,
    "g": 5,  "h": 4,  "i": 34, "j": 38, "k": 40, "l": 37,
    "m": 46, "n": 45, "o": 31, "p": 35, "q": 12, "r": 15,
    "s": 1,  "t": 17, "u": 32, "v": 9,  "w": 13, "x": 7,
    "y": 16, "z": 6,
}

_MOD_FLAG_MAP: dict[str, int] = {
    "ctrl":    0x40000,   # NSEventModifierFlagControl
    "control": 0x40000,
    "shift":   0x20000,   # NSEventModifierFlagShift
    "alt":     0x80000,   # NSEventModifierFlagOption
    "option":  0x80000,
    "cmd":     0x100000,  # NSEventModifierFlagCommand
    "command": 0x100000,
}


def _parse_hotkey(hotkey_str: str) -> str:
    """Convert config-style hotkey strings to pynput HotKey format (kept for display)."""
    if "<" in hotkey_str:
        return hotkey_str
    parts = [p.strip() for p in hotkey_str.split("+")]
    converted = []
    for part in parts:
        low = part.lower()
        if low in _MOD_FLAG_MAP or low in _KEYCODE_MAP or len(part) > 1:
            converted.append(f"<{low}>")
        else:
            converted.append(part)
    return "+".join(converted)


def _is_fn_config(hotkey_str: str) -> bool:
    return hotkey_str.strip().lower().lstrip("<").rstrip(">") == "fn"


def _parse_to_native(hotkey_str: str) -> tuple[Optional[int], int]:
    """Return (keycode, mod_flags) for a hotkey string like 'ctrl+shift+space'."""
    clean = hotkey_str.replace("<", "").replace(">", "").lower()
    parts = [p.strip() for p in clean.split("+")]
    mod_flags = 0
    keycode = None
    for part in parts:
        if part in _MOD_FLAG_MAP:
            mod_flags |= _MOD_FLAG_MAP[part]
        elif part in _KEYCODE_MAP:
            keycode = _KEYCODE_MAP[part]
        elif len(part) == 1:
            keycode = _KEYCODE_MAP.get(part)
    return keycode, mod_flags


# ── HotkeyListener ────────────────────────────────────────────────────────────

class HotkeyListener:
    """
    Toggle-mode global hotkey listener using NSEvent (no pynput/ScriptMonitor).

    Each press of the configured key combination calls `on_activate`.
    The NSEvent monitor is registered on the AppKit main-thread run loop
    (scheduled via NSOperationQueue.mainQueue) so it must be started after
    rumps / NSApplication has begun running.
    """

    def __init__(self, hotkey: str = "ctrl+shift+space", on_activate: Optional[Callable] = None):
        self._hotkey_str = _parse_hotkey(hotkey)
        self.on_activate = on_activate
        self._monitor = None
        self._running = False
        self._keycode, self._mod_flags = _parse_to_native(hotkey)

        if self._keycode is None:
            logger.warning(
                "Could not parse keycode from hotkey %r — hotkey may not fire", hotkey
            )

    @property
    def hotkey_str(self) -> str:
        return self._hotkey_str

    @property
    def is_running(self) -> bool:
        return self._running

    def start(self) -> None:
        if self._running:
            return
        self._running = True

        try:
            import AppKit

            keycode = self._keycode
            mod_flags = self._mod_flags
            on_activate = self.on_activate

            def _create_monitor():
                def _handler(event):
                    try:
                        if event.isARepeat():
                            return
                        flags = event.modifierFlags() & _MOD_MASK
                        if event.keyCode() == keycode and (flags & mod_flags) == mod_flags:
                            if on_activate:
                                threading.Thread(target=on_activate, daemon=True).start()
                    except Exception:
                        logger.debug("Error in NSEvent hotkey handler", exc_info=True)

                self._monitor = AppKit.NSEvent.addGlobalMonitorForEventsMatchingMask_handler_(
                    _NSKeyDownMask, _handler
                )
                logger.info("NSEvent hotkey listener started: %s", self._hotkey_str)

            AppKit.NSOperationQueue.mainQueue().addOperationWithBlock_(_create_monitor)

        except ImportError:
            logger.warning("AppKit not available — falling back to pynput for hotkey")
            self._start_pynput_fallback()

    def stop(self) -> None:
        self._running = False
        if self._monitor is not None:
            try:
                import AppKit
                AppKit.NSEvent.removeMonitor_(self._monitor)
            except Exception:
                logger.debug("Failed to remove NSEvent monitor", exc_info=True)
            self._monitor = None
        logger.info("HotkeyListener stopped")

    def update_hotkey(self, new_hotkey: str, on_activate: Optional[Callable] = None) -> None:
        was_running = self._running
        self.stop()
        self._hotkey_str = _parse_hotkey(new_hotkey)
        self._keycode, self._mod_flags = _parse_to_native(new_hotkey)
        if on_activate is not None:
            self.on_activate = on_activate
        if was_running:
            self.start()

    def _start_pynput_fallback(self) -> None:
        from pynput import keyboard

        def _on_hotkey():
            if self.on_activate:
                threading.Thread(target=self.on_activate, daemon=True).start()

        self._pynput_listener = keyboard.GlobalHotKeys(
            {self._hotkey_str: _on_hotkey}, suppress=False
        )
        self._pynput_listener.daemon = True
        self._pynput_listener.start()
        logger.info("pynput hotkey fallback started: %s", self._hotkey_str)


# ── FnHoldListener ────────────────────────────────────────────────────────────

class FnHoldListener:
    """
    Hold-to-record listener for the bare Fn key.

    Press Fn → calls `on_press`.  Release Fn → calls `on_release`.

    Fn has no NSEvent keycode so we keep pynput here.
    """

    def __init__(
        self,
        on_press: Optional[Callable] = None,
        on_release: Optional[Callable] = None,
    ):
        self.on_press_cb = on_press
        self.on_release_cb = on_release
        self._listener = None
        self._running = False

    @property
    def hotkey_str(self) -> str:
        return "<fn>"

    @property
    def is_running(self) -> bool:
        return self._running

    def start(self) -> None:
        if self._running:
            return

        from pynput import keyboard

        fn_key = getattr(keyboard.Key, "fn", None)
        if fn_key is None:
            logger.warning("pynput does not expose Key.fn — Fn key detection unavailable")

        def _on_press(key):
            if fn_key is not None and key == fn_key:
                if self.on_press_cb:
                    threading.Thread(target=self.on_press_cb, daemon=True).start()

        def _on_release(key):
            if fn_key is not None and key == fn_key:
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


# ── Factory ───────────────────────────────────────────────────────────────────

def create_listener(
    hotkey: str,
    on_activate: Optional[Callable] = None,
    on_start: Optional[Callable] = None,
    on_stop: Optional[Callable] = None,
):
    if _is_fn_config(hotkey):
        logger.info("Using Fn hold-to-record mode")
        return FnHoldListener(on_press=on_start, on_release=on_stop)
    else:
        logger.info("Using toggle mode for hotkey: %s", hotkey)
        return HotkeyListener(hotkey=hotkey, on_activate=on_activate)
