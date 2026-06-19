"""
Text insertion via NSPasteboard + simulated Cmd+V.

Saves and restores the original clipboard contents so the user's
copied data is not lost after dictation.

When running inside Tacet.app (C launcher), Cmd+V is dispatched back
to the parent C process via a pipe (TACET_PASTE_FD). The C binary
calls CGEventPost with its own Accessibility grant, bypassing the
Python.framework code-identity issue where python3's separate TCC
identity would require a duplicate Accessibility entry.
"""
import ctypes
import ctypes.util
import fcntl
import logging
import os
import time
from typing import Optional

import pyperclip

logger = logging.getLogger(__name__)

_RESTORE_DELAY = 0.1  # seconds to wait before restoring clipboard

# When TACET_PASTE_FD is set, the C launcher handles CGEventPost.
# We set FD_CLOEXEC immediately so mlx multiprocessing workers don't
# inherit the write end and accidentally keep the pipe open.
_PASTE_FD: Optional[int] = None
_paste_fd_env = os.environ.get("TACET_PASTE_FD")
if _paste_fd_env is not None:
    try:
        _fd = int(_paste_fd_env)
        fcntl.fcntl(_fd, fcntl.F_SETFD, fcntl.FD_CLOEXEC)
        _PASTE_FD = _fd
    except (ValueError, OSError):
        pass


def insert_text(text: str, restore_clipboard: bool = True) -> bool:
    """
    Insert `text` into the currently focused application.

    Steps:
      1. Save current clipboard contents
      2. Copy `text` to clipboard
      3. Simulate Cmd+V (via C launcher pipe or direct CGEventPost)
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
    Send Cmd+V. When TACET_PASTE_FD is set, delegates to the C launcher
    (which has the Accessibility grant). Otherwise falls back to direct
    CGEventPost (requires Accessibility on python3 itself).
    """
    if _PASTE_FD is not None:
        try:
            os.write(_PASTE_FD, b"P")
            logger.debug("Cmd+V dispatched to C launcher via paste pipe")
            return True
        except OSError:
            logger.exception("Failed to write to paste pipe — falling back to CGEventPost")

    return _cgeventpost_paste()


def _cgeventpost_paste() -> bool:
    """
    Send Cmd+V directly via CoreGraphics CGEventPost.
    Requires Accessibility permission on the calling process.
    """
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
    Check if Accessibility permission is available for text insertion.
    Returns True if the C launcher pipe is active (it handles this),
    or if python3 itself has been granted Accessibility access.
    """
    if _PASTE_FD is not None:
        return True  # C launcher holds the Accessibility grant and does CGEventPost

    try:
        lib_path = ctypes.util.find_library("ApplicationServices")
        if not lib_path:
            return True
        lib = ctypes.cdll.LoadLibrary(lib_path)
        lib.AXIsProcessTrusted.restype = ctypes.c_bool
        return bool(lib.AXIsProcessTrusted())
    except Exception:
        return True  # Can't determine — assume OK
