"""
Floating status overlay window.

Shows recording / processing / done states using a small, borderless
window anchored at the bottom-center of the screen.

Uses PyObjC (AppKit) to create a native NSPanel that floats above all
other windows and requires no app focus.
"""
import logging
import threading
from enum import Enum, auto
from typing import Optional

logger = logging.getLogger(__name__)


class OverlayState(Enum):
    HIDDEN = auto()
    RECORDING = auto()
    PROCESSING = auto()
    DONE = auto()
    ERROR = auto()


# Text labels for each state
_STATE_LABELS = {
    OverlayState.RECORDING: "● Recording…",
    OverlayState.PROCESSING: "⏳ Processing…",
    OverlayState.DONE: "✓ Done",
    OverlayState.ERROR: "✗ Error",
}

_AUTO_HIDE_DELAY = 1.5  # seconds to show DONE/ERROR before hiding


class StatusOverlay:
    """
    Floating status indicator anchored at the bottom-center of the screen.

    Falls back gracefully if AppKit is not available (e.g., in testing).
    """

    def __init__(self, position: str = "bottom-center"):
        self.position = position
        self._state = OverlayState.HIDDEN
        self._window = None
        self._label = None
        self._hide_timer: Optional[threading.Timer] = None
        self._appkit_available = self._init_appkit()

    def _init_appkit(self) -> bool:
        """Try to import AppKit and set up the NSPanel."""
        try:
            import AppKit
            import objc
            self._AppKit = AppKit
            self._objc = objc
            return True
        except ImportError:
            logger.warning(
                "PyObjC/AppKit not available — overlay disabled. "
                "Install pyobjc-framework-Cocoa to enable it."
            )
            return False

    def _create_window(self):
        """Create the floating NSPanel (called once, lazily)."""
        if not self._appkit_available or self._window is not None:
            return

        AppKit = self._AppKit

        # Window dimensions
        width, height = 220, 44
        screen = AppKit.NSScreen.mainScreen()
        screen_frame = screen.frame()

        # Bottom-center position
        x = (screen_frame.size.width - width) / 2
        y = 40  # Pixels from bottom

        frame = AppKit.NSMakeRect(x, y, width, height)

        # Borderless, floating panel
        style = (
            AppKit.NSWindowStyleMaskBorderless
        )
        self._window = AppKit.NSPanel.alloc().initWithContentRect_styleMask_backing_defer_(
            frame,
            style,
            AppKit.NSBackingStoreBuffered,
            False,
        )
        self._window.setLevel_(AppKit.NSFloatingWindowLevel + 1)
        self._window.setOpaque_(False)
        self._window.setBackgroundColor_(AppKit.NSColor.clearColor())
        self._window.setHasShadow_(True)
        self._window.setCollectionBehavior_(
            AppKit.NSWindowCollectionBehaviorCanJoinAllSpaces
            | AppKit.NSWindowCollectionBehaviorStationary
            | AppKit.NSWindowCollectionBehaviorIgnoresCycle
        )

        # Text label
        label_frame = AppKit.NSMakeRect(0, 0, width, height)
        self._label = AppKit.NSTextField.alloc().initWithFrame_(label_frame)
        self._label.setStringValue_("")
        self._label.setAlignment_(AppKit.NSTextAlignmentCenter)
        self._label.setTextColor_(AppKit.NSColor.whiteColor())
        self._label.setBackgroundColor_(AppKit.NSColor.clearColor())
        self._label.setBordered_(False)
        self._label.setEditable_(False)
        self._label.setSelectable_(False)
        font = AppKit.NSFont.systemFontOfSize_weight_(14, AppKit.NSFontWeightMedium)
        self._label.setFont_(font)

        content_view = self._window.contentView()
        content_view.setWantsLayer_(True)
        layer = content_view.layer()
        layer.setCornerRadius_(12.0)
        layer.setMasksToBounds_(True)
        layer.setBackgroundColor_(
            AppKit.NSColor.colorWithCalibratedRed_green_blue_alpha_(
                0.1, 0.1, 0.1, 0.88
            ).CGColor()
        )
        content_view.addSubview_(self._label)

    def set_state(self, state: OverlayState) -> None:
        """Update the overlay to show the given state."""
        # Cancel any pending auto-hide
        if self._hide_timer:
            self._hide_timer.cancel()
            self._hide_timer = None

        self._state = state

        if not self._appkit_available:
            logger.debug(f"Overlay state: {state.name}")
            return

        # Schedule UI update on main thread
        try:
            import AppKit
            AppKit.NSThread.isMainThread()  # Just to confirm AppKit is usable

            def _update():
                try:
                    self._create_window()
                    if state == OverlayState.HIDDEN:
                        if self._window is not None:
                            self._window.orderOut_(None)
                        return
                    if self._window is None or self._label is None:
                        return
                    label = _STATE_LABELS.get(state, "")
                    self._label.setStringValue_(label)
                    self._window.orderFrontRegardless()
                except Exception:
                    logger.debug(f"Overlay _update failed for state {state.name}", exc_info=True)

            AppKit.NSOperationQueue.mainQueue().addOperationWithBlock_(_update)

            # Auto-hide after DONE / ERROR
            if state in (OverlayState.DONE, OverlayState.ERROR):
                self._hide_timer = threading.Timer(
                    _AUTO_HIDE_DELAY, lambda: self.set_state(OverlayState.HIDDEN)
                )
                self._hide_timer.daemon = True
                self._hide_timer.start()

        except Exception:
            logger.debug(f"Overlay update failed for state {state.name}", exc_info=True)

    def show_recording(self):
        self.set_state(OverlayState.RECORDING)

    def show_processing(self):
        self.set_state(OverlayState.PROCESSING)

    def show_done(self):
        self.set_state(OverlayState.DONE)

    def show_error(self):
        self.set_state(OverlayState.ERROR)

    def hide(self):
        self.set_state(OverlayState.HIDDEN)
