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

    time.sleep(0.05)  # let the clipboard settle before simulating paste
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
    Send Cmd+V via CoreGraphics CGEventPost (no osascript, no ScriptMonitor).
    Returns True on success.
    """
    import ctypes
    try:
        CG = ctypes.cdll.LoadLibrary(
            "/System/Library/Frameworks/CoreGraphics.framework/CoreGraphics"
        )
        CF = ctypes.cdll.LoadLibrary(
            "/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation"
        )

        CG.CGEventSourceCreate.restype = ctypes.c_void_p
        CG.CGEventSourceCreate.argtypes = [ctypes.c_int]
        CG.CGEventCreateKeyboardEvent.restype = ctypes.c_void_p
        CG.CGEventCreateKeyboardEvent.argtypes = [ctypes.c_void_p, ctypes.c_uint16, ctypes.c_bool]
        CG.CGEventSetFlags.restype = None
        CG.CGEventSetFlags.argtypes = [ctypes.c_void_p, ctypes.c_uint64]
        CG.CGEventPost.restype = None
        CG.CGEventPost.argtypes = [ctypes.c_int, ctypes.c_void_p]
        CF.CFRelease.restype = None
        CF.CFRelease.argtypes = [ctypes.c_void_p]

        kCGHIDEventTap = 0
        kCGEventSourceStateCombinedSessionState = 1
        kCGEventFlagMaskCommand = 1 << 20
        V_KEYCODE = 9

        src = CG.CGEventSourceCreate(kCGEventSourceStateCombinedSessionState)

        v_down = CG.CGEventCreateKeyboardEvent(src, V_KEYCODE, True)
        CG.CGEventSetFlags(v_down, kCGEventFlagMaskCommand)
        CG.CGEventPost(kCGHIDEventTap, v_down)
        CF.CFRelease(v_down)

        v_up = CG.CGEventCreateKeyboardEvent(src, V_KEYCODE, False)
        CG.CGEventSetFlags(v_up, kCGEventFlagMaskCommand)
        CG.CGEventPost(kCGHIDEventTap, v_up)
        CF.CFRelease(v_up)

        CF.CFRelease(src)

        logger.debug("Cmd+V simulated via CGEventPost")
        return True
    except Exception:
        logger.exception("CGEventPost paste failed")
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
