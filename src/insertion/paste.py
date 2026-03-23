"""
Text insertion via NSPasteboard + simulated Cmd+V.

Saves and restores the original clipboard contents so the user's
copied data is not lost after dictation.
"""
import ctypes
import ctypes.util
import logging
import time
from typing import Optional

import pyperclip

logger = logging.getLogger(__name__)

_RESTORE_DELAY = 0.1  # seconds to wait before restoring clipboard


def insert_text(text: str, restore_clipboard: bool = True) -> bool:
    """
    Insert `text` into the currently focused application.

    Steps:
      1. Save current clipboard contents
      2. Copy `text` to clipboard
      3. Simulate Cmd+V via pynput keyboard controller
      4. Restore original clipboard after a short delay

    Returns True on success, False on failure.
    """
    if not text:
        logger.warning("insert_text called with empty text")
        return False

    original_clipboard: Optional[str] = None

    if restore_clipboard:
        try:
            original_clipboard = pyperclip.paste()
        except Exception:
            logger.debug("Could not read current clipboard — will not restore")

    try:
        pyperclip.copy(text)
        logger.debug(f"Copied to clipboard: {text!r}")
    except Exception:
        logger.exception("Failed to copy text to clipboard")
        return False

    success = _simulate_paste()

    if restore_clipboard and original_clipboard is not None:
        # Small delay to ensure the paste completes before we swap the clipboard back
        time.sleep(_RESTORE_DELAY)
        try:
            pyperclip.copy(original_clipboard)
            logger.debug("Clipboard restored")
        except Exception:
            logger.debug("Failed to restore clipboard")

    return success


def _simulate_paste() -> bool:
    """
    Send Cmd+V to the frontmost application via pynput keyboard controller.
    Returns True on success.
    """
    try:
        from pynput.keyboard import Controller as KeyboardController, Key
        kb = KeyboardController()
        kb.press(Key.cmd)
        kb.press('v')
        kb.release('v')
        kb.release(Key.cmd)
        logger.debug("Cmd+V simulated successfully")
        return True
    except Exception:
        logger.exception("Unexpected error during paste simulation")
        return False


def check_accessibility_permission() -> bool:
    """
    Check if the app has Accessibility permission (required for Cmd+V simulation).
    Returns True if the check passes or is inconclusive.
    """
    try:
        lib_path = ctypes.util.find_library("ApplicationServices")
        if not lib_path:
            return True
        lib = ctypes.cdll.LoadLibrary(lib_path)
        lib.AXIsProcessTrusted.restype = ctypes.c_bool
        return bool(lib.AXIsProcessTrusted())
    except Exception:
        return True  # Can't determine — assume OK
